import re
import asyncpg
import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional, Tuple, Dict, Any, cast

try:
    import config_local as config  # type: ignore
except ImportError:
    import config  # type: ignore

from utils.logger import logger
from utils.checks_interaction import is_owner_or_admin_interaction


def _normalize(text: str) -> List[str]:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    tokens = [t for t in text.split() if len(t) >= 3]
    return tokens


def _score_entry(query_tokens: List[str], entry: Dict[str, Any]) -> int:
    hay = " ".join([
        entry.get("summary") or "",
        " ".join(entry.get("keywords") or []),
        entry.get("title") or "",
    ])
    tokens = set(_normalize(hay))
    return sum(1 for t in query_tokens if t in tokens)


class FAQ(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.conn: Optional[asyncpg.Connection] = None
        self.bot.loop.create_task(self._setup_db())

    async def _setup_db(self) -> None:
        try:
            self.conn = await asyncpg.connect(config.DATABASE_URL)
            # Ensure columns on faq_entries
            await self.conn.execute("ALTER TABLE faq_entries ADD COLUMN IF NOT EXISTS title TEXT;")
            await self.conn.execute("ALTER TABLE faq_entries ADD COLUMN IF NOT EXISTS keywords TEXT[];")
            # Logs table
            await self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS faq_search_logs (
                  id SERIAL PRIMARY KEY,
                  query TEXT NOT NULL,
                  match_count INT NOT NULL,
                  created_at TIMESTAMPTZ DEFAULT NOW()
                );
                """
            )
            logger.info("✅ FAQ: DB ready")
        except Exception as e:
            logger.error(f"❌ FAQ: DB init error: {e}")

    async def _fetch_entries(self) -> List[asyncpg.Record]:
        if not self.conn:
            return []
        rows = await self.conn.fetch("SELECT id, title, summary, keywords, created_at FROM faq_entries ORDER BY created_at DESC")
        return rows

    async def _search_entries(self, query: str, limit: int = 5) -> List[asyncpg.Record]:
        rows = await self._fetch_entries()
        q_tokens = _normalize(query)
        scored = []
        for r in rows:
            score = _score_entry(q_tokens, dict(r))
            if score > 0:
                scored.append((score, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = [r for _, r in scored[:limit]]
        # log
        try:
            if self.conn:
                await self.conn.execute("INSERT INTO faq_search_logs (query, match_count) VALUES ($1, $2)", query, len(results))
        except Exception:
            pass
        return results

    # --- Slash group
    faq = app_commands.Group(name="faq", description="FAQ commands")

    @faq.command(name="list", description="Show latest FAQ entries (last 10)")
    async def faq_list(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        rows = await self._fetch_entries()
        rows = rows[:10]
        if not rows:
            await interaction.followup.send("No FAQ entries yet.", ephemeral=True)
            return
        embed = discord.Embed(title="📚 FAQ – Latest", color=discord.Color.blurple())
        for r in rows:
            title = r.get("title") or f"Entry #{r['id']}"
            preview = (r.get("summary") or "-")
            if len(preview) > 140:
                preview = preview[:140] + "…"
            embed.add_field(name=f"[{r['id']}] {title}", value=preview, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @faq.command(name="view", description="View a FAQ entry by ID")
    @app_commands.describe(id="FAQ entry ID")
    async def faq_view(self, interaction: discord.Interaction, id: int):
        await interaction.response.defer(ephemeral=True)
        if not self.conn:
            await interaction.followup.send("Database not connected.", ephemeral=True)
            return
        row = await self.conn.fetchrow("SELECT id, title, summary, keywords, created_at FROM faq_entries WHERE id = $1", id)
        if not row:
            await interaction.followup.send("Entry not found.", ephemeral=True)
            return
        title = row.get("title") or f"Entry #{row['id']}"
        embed = discord.Embed(title=f"📖 {title}", description=row.get("summary") or "-", color=discord.Color.green())
        kws = row.get("keywords") or []
        if kws:
            embed.add_field(name="Keywords", value=", ".join(kws), inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @faq.command(name="search", description="Search in FAQ entries")
    @app_commands.describe(query="Your question or keywords")
    async def faq_search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        results = await self._search_entries(query, limit=5)
        if not results:
            await interaction.followup.send("No results.", ephemeral=True)
            return
        embed = discord.Embed(title="🔎 FAQ – Top results", color=discord.Color.orange())
        for r in results:
            title = r.get("title") or f"Entry #{r['id']}"
            preview = (r.get("summary") or "-")
            if len(preview) > 160:
                preview = preview[:160] + "…"
            embed.add_field(name=f"[{r['id']}] {title}", value=preview, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @faq_search.autocomplete("query")
    async def faq_search_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        # quick suggestion based on titles/keywords
        choices: List[app_commands.Choice[str]] = []
        try:
            rows = await self._fetch_entries()
            current_norm = current.lower()
            for r in rows[:25]:
                title = (r.get("title") or "").strip()
                keywords = r.get("keywords") or []
                if (title and current_norm in title.lower()) or any(current_norm in (k or "").lower() for k in keywords):
                    label = title or f"Entry #{r['id']}"
                    choices.append(app_commands.Choice(name=label[:100], value=label))
                    if len(choices) >= 15:
                        break
        except Exception:
            pass
        return choices

    @faq.command(name="reload", description="Reload FAQ index (admin)")
    async def faq_reload(self, interaction: discord.Interaction):
        if not await is_owner_or_admin_interaction(interaction):
            await interaction.response.send_message("⛔ Admins only.", ephemeral=True)
            return
        await interaction.response.send_message("✅ FAQ index reload queued (in-memory).", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(FAQ(bot))


