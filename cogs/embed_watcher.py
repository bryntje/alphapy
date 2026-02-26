import discord
from discord import app_commands
from discord.ext import commands
import re
from datetime import datetime, timedelta
import config
import asyncpg
from asyncpg import exceptions as pg_exceptions
from typing import Optional, Tuple, List, cast
from utils.logger import logger
from utils.timezone import BRUSSELS_TZ
from utils.settings_service import SettingsService
from utils.settings_helpers import CachedSettingsHelper
from utils.db_helpers import acquire_safe, is_pool_healthy
from utils.embed_builder import EmbedBuilder
from utils.parsers import parse_days_string, format_days_for_display
from utils.sanitizer import safe_embed_text
import json


# All logging timestamps in this module use Brussels time for clarity.

def extract_datetime_from_text(text: str) -> Optional[datetime]:
    """Parse a free-text date/time, trying numeric and natural language formats."""
    # Try numeric date like 12/05/2025 or 12-05-25
    date_match = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", text)
    time_match = re.search(r"(\d{1,2}[:.]\d{2})", text)
    current_year = datetime.now(BRUSSELS_TZ).year

    if date_match and time_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        year = date_match.group(3)
        if year:
            year = int(year) if len(year) == 4 else 2000 + int(year)
        else:
            year = current_year
        time_str = time_match.group(1).replace(".", ":")
        try:
            dt = datetime.strptime(f"{day}/{month}/{year} {time_str}", "%d/%m/%Y %H:%M")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BRUSSELS_TZ)
            return dt
        except Exception as e:
            logger.warning(f"⛔️ Date parse failed: {e}")

    # Try natural language date like 12th May
    date_match = re.search(r"(\d{1,2})(st|nd|rd|th)?\s+([A-Z][a-z]+)", text)
    if date_match and time_match:
        day = int(date_match.group(1))
        month_str = date_match.group(3)
        time_str = time_match.group(1).replace(".", ":")
        try:
            dt = datetime.strptime(f"{day} {month_str} {current_year} {time_str}", "%d %B %Y %H:%M")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=BRUSSELS_TZ)
            return dt
        except Exception as e:
            logger.warning(f"⛔️ Date parse failed: {e}")
    return None


class EmbedReminderWatcher(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[asyncpg.Pool] = None
        settings = getattr(bot, "settings", None)
        if settings is None or not hasattr(settings, 'get'):
            raise RuntimeError("SettingsService not available on bot instance")
        self.settings = settings  # type: ignore
        self.settings_helper = CachedSettingsHelper(settings)  # type: ignore
    
    def format_days_for_display(self, days_list: List[str]) -> str:
        """Convert day numbers to readable day names using centralized parser."""
        return format_days_for_display(days_list) or "—"

    async def setup_db(self) -> None:
        try:
            from utils.db_helpers import create_db_pool
            self.db = await create_db_pool(
                config.DATABASE_URL,
                name="embed_watcher",
                min_size=1,
                max_size=10,
                command_timeout=10.0
            )
        except Exception as e:
            logger.error(f"❌ EmbedWatcher: DB pool creation error: {e}")
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return  # Skip messages not in a guild
        
        announcements_channel_id = self._get_announcements_channel_id(message.guild.id)
        if message.channel.id != announcements_channel_id:
            return
        
        is_bot_message = message.author.id == getattr(self.bot.user, 'id', None)
        
        # Skip messages from the bot itself unless processing bot messages is enabled
        if is_bot_message:
            if not self._is_process_bot_messages_enabled(message.guild.id):
                return
        
        # Loop protection: Check if we already processed this message (for both bot and user messages)
        # This prevents duplicate reminders from the same message
        if is_pool_healthy(self.db):
            existing = await self._check_existing_reminder_for_message(message.guild.id, message.channel.id, message.id)
            if existing:
                logger.info(f"⏭️ Message {message.id} already has a reminder (ID: {existing}) - skipping to prevent duplicate processing")
                await self._log_message_processed(message, "skipped", f"Already processed (reminder ID: {existing})", message.guild.id)
                return
            
            # Additional check: if this is a bot message, check if a similar reminder already exists
            # This prevents loops when bot_messages is enabled and the bot sees its own reminder embeds
            if is_bot_message and message.embeds:
                embed = message.embeds[0]
                # Check if this embed is already a reminder (has auto-reminder footer or similar title pattern)
                if embed.footer and "auto-reminder" in (embed.footer.text or "").lower():
                    logger.info(f"⏭️ Bot message {message.id} is already a reminder embed - skipping to prevent loop")
                    await self._log_message_processed(message, "skipped", "Bot reminder embed detected", message.guild.id)
                    return
                # Check if a reminder with similar title already exists (within last 5 minutes)
                if embed.title:
                    similar = await self._check_similar_reminder_exists(
                        message.guild.id, 
                        embed.title, 
                        message.channel.id
                    )
                    if similar:
                        logger.info(f"⏭️ Similar reminder already exists for bot message {message.id} - skipping to prevent duplicate")
                        await self._log_message_processed(message, "skipped", f"Similar reminder exists (ID: {similar})", message.guild.id)
                        return
        
        # Check for embeds first
        message_type = "embed"
        embed_source = None
        
        if message.embeds:
            embed = message.embeds[0]
            embed_source = embed
            
            # ⛔️ Skip reminders that the bot itself has already posted (to avoid loops)
            # Check for auto-reminder footer (from reminder system)
            if embed.footer and embed.footer.text == "auto-reminder":
                await self._log_message_processed(message, "skipped", "Auto-reminder tag detected", message.guild.id)
                return
            
            # Additional loop protection: Check embed footer for "processed" markers
            # (Future: we could add a marker when we create reminders from embeds)
            if embed.footer and "embedwatcher-processed" in (embed.footer.text or "").lower():
                return
            
            if isinstance(message.channel, (discord.TextChannel, discord.Thread)):
                channel_name = message.channel.mention
            else:
                channel_name = f"#{getattr(message.channel, 'name', 'unknown')}" if hasattr(message.channel, 'name') else str(message.channel.id)
            logger.info(f"📥 Processing embed message from {message.author} in {channel_name} (ID: {message.id})")
            parsed = await self.parse_embed_for_reminder(embed, message.guild.id)
            if not parsed:
                logger.warning(f"⚠️ Failed to parse embed message {message.id} - parse_embed_for_reminder returned None")
                await self._log_message_processed(message, "failed", "Parse returned None - check logs for details", message.guild.id)
                await self._log_failed_parse(embed, message.guild.id, message, "embed")
                return
        # Check for non-embed messages if enabled
        elif self._is_non_embed_enabled(message.guild.id) and message.content:
            message_type = "text"
            # Convert message to a mock embed for parsing
            title_text = message.content[:256] if len(message.content) > 100 else message.content[:100] if message.content else "Message"
            mock_embed = EmbedBuilder.info(
                title=title_text,
                description=message.content
            )
            embed_source = mock_embed
            if isinstance(message.channel, (discord.TextChannel, discord.Thread)):
                channel_name = message.channel.mention
            else:
                channel_name = f"#{getattr(message.channel, 'name', 'unknown')}" if hasattr(message.channel, 'name') else str(message.channel.id)
            logger.info(f"📥 Processing text message from {message.author} in {channel_name} (ID: {message.id})")
            parsed = await self.parse_embed_for_reminder(mock_embed, message.guild.id)
        else:
            return

        if parsed and parsed["reminder_time"]:
            # Successfully parsed
            logger.info(f"✅ Successfully parsed {message_type} message (ID: {message.id}) - reminder scheduled for {parsed['datetime'].strftime('%d/%m/%Y %H:%M')}")
            
            log_channel_id = self._get_log_channel_id(message.guild.id)
            log_channel = self.bot.get_channel(log_channel_id)
            if isinstance(log_channel, (discord.TextChannel, discord.Thread)):
                if isinstance(message.channel, (discord.TextChannel, discord.Thread)):
                    channel_ref = message.channel.mention
                else:
                    channel_ref = f"#{getattr(message.channel, 'name', 'unknown')}" if hasattr(message.channel, 'name') else str(message.channel.id)
                
                # Create embed for cleaner log display using EmbedBuilder
                log_embed = EmbedBuilder.success(
                    title="🔔 Auto-reminder Detected",
                    description=f"Reminder automatically created from {message_type} message"
                )
                log_embed.add_field(
                    name="📌 Title",
                    value=safe_embed_text((parsed.get("title") or "—")[:1024], 1024),
                    inline=False
                )
                log_embed.add_field(
                    name="📅 Event Date & Time",
                    value=f"{parsed['datetime'].strftime('%A %d %B %Y')} at {parsed['datetime'].strftime('%H:%M')}",
                    inline=True
                )
                log_embed.add_field(
                    name="⏰ Reminder Time",
                    value=f"Will trigger at {parsed['reminder_time'].strftime('%H:%M')}",
                    inline=True
                )
                if parsed.get("location") and parsed.get("location") != "-":
                    log_embed.add_field(
                        name="📍 Location",
                        value=safe_embed_text(parsed.get("location", "")[:1024], 1024),
                        inline=True
                    )
                log_embed.add_field(
                    name="📝 Message Type",
                    value=message_type.capitalize(),
                    inline=True
                )
                if parsed.get('days'):
                    days_display = self.format_days_for_display(parsed['days'])
                    log_embed.add_field(
                        name="📆 Recurring Days",
                        value=days_display,
                        inline=True
                    )
                log_embed.set_footer(text=f"Author: {message.author.display_name} | Channel: {channel_ref}")
                log_embed.url = message.jump_url
                
                await log_channel.send(embed=log_embed)
            else:
                logger.warning("⚠️ Log channel not found or not accessible.")

            if is_pool_healthy(self.db):
                # Additional loop protection: Mark this message as processed by storing it
                # This prevents the same message from being processed again if it gets re-triggered
                await self.store_parsed_reminder(
                    parsed, 
                    int(message.channel.id), 
                    int(message.author.id), 
                    message.guild.id,
                    origin_channel_id=int(message.channel.id),
                    origin_message_id=int(message.id)
                )
                
                # For bot messages: Add a marker to prevent future loops
                if is_bot_message:
                    logger.info(f"🔒 Marked bot message {message.id} as processed to prevent loops")
            else:
                logger.warning(f"⚠️ Database connection not available - reminder not stored for message {message.id}")
        else:
            # Failed to parse
            reason = "No date/time information found"
            if embed_source:
                await self._log_failed_parse(embed_source, message.guild.id, message, message_type)
            logger.info(f"⚠️ Failed to parse {message_type} message (ID: {message.id}) - {reason}")
            await self._log_message_processed(message, "failed", reason, message.guild.id)

    async def parse_embed_for_reminder(self, embed: discord.Embed, guild_id: int) -> Optional[dict]:
        all_text = embed.description or ""
        title_text = embed.title or ""
        
        # Include footer text in all_text for parsing (if present)
        if embed.footer and embed.footer.text:
            all_text += f"\n{embed.footer.text}"
        
        for field in embed.fields:
            all_text += f"\n{field.name}\n{field.value}"

        lines = all_text.split('\n')
        date_line, time_line, location_line, days_line = self.extract_fields_from_lines(lines)

        # Fallback: if the "Time" line includes a concrete date, extract it so
        # one-off messages such as "Wednesday, October 01/10/25 – 19:30" are
        # recognised as dated events instead of recurring reminders.
        inferred_date = None
        if not date_line and time_line:
            inferred_date = self.infer_date_from_time_line(time_line)
            if inferred_date:
                date_line = inferred_date

        # Fallbacks for time and days if not present in structured lines
        if not time_line:
            time_fallback = re.search(r"\b(\d{1,2}[:.]\d{2})\s*(?:CET|CEST)?", embed.description or "")
            if not time_fallback:
                time_fallback = re.search(r"\b(\d{1,2}[:.]\d{2})\s*(?:CET|CEST)?", all_text)
            if time_fallback:
                time_line = time_fallback.group(0)

        # Try to extract relative dates like "This Wednesday", "Next Friday" from title or description
        if not date_line:
            relative_date = self.parse_relative_date(title_text + " " + (embed.description or ""))
            if relative_date:
                date_line = relative_date
                logger.info(f"✅ Parsed relative date: {date_line}")

        if not days_line and embed.description:
            day_fallback = re.search(r"\b(?:every|elke)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", embed.description, re.IGNORECASE)
            if day_fallback:
                days_line = day_fallback.group(1)

        try:
            dt, tz = self.parse_datetime(date_line, time_line)

            # Track whether we found a concrete calendar date
            had_explicit_date = bool(date_line)
            dt_from_description = False

            # Fallback: try to parse datetime from the description when
            # no explicit date/time fields were found.
            if not dt:
                parsed_from_description = extract_datetime_from_text(embed.description or "")
                if parsed_from_description:
                    dt = parsed_from_description
                    tz = BRUSSELS_TZ
                    dt_from_description = True

            # Fallback: attempt to extract location from the description if no
            # location field exists.
            if not location_line and embed.description:
                loc_match = re.search(r"(?:location|locatie)[:\s]*([^\n]+)", embed.description, re.IGNORECASE)
                if loc_match:
                    location_line = loc_match.group(1).strip()

            if not dt:
                # Try Grok fallback if enabled
                if self._is_gpt_fallback_enabled(guild_id):
                    gpt_parsed = await self._parse_with_gpt_fallback(embed, guild_id)
                    if gpt_parsed and gpt_parsed.get("datetime"):
                        # Use Grok parsed result
                        dt_gpt = gpt_parsed.get("datetime")
                        if dt_gpt:
                            reminder_time = dt_gpt - timedelta(minutes=self._get_reminder_offset(guild_id))
                        else:
                            reminder_time = None
                        if not dt_gpt or not reminder_time:
                            logger.warning("⚠️ Grok fallback returned invalid datetime")
                            await self._log_failed_parse(embed, guild_id)
                            return None
                        days_list = gpt_parsed.get("days", [])
                        location_from_gpt = gpt_parsed.get("location", "-")
                        logger.info(f"✅ Grok fallback parsing succeeded for embed: {embed.title}")
                        return {
                            "datetime": dt_gpt,
                            "reminder_time": reminder_time,
                            "location": location_from_gpt,
                            "title": embed.title or "-",
                            "description": embed.description or "-",
                            "days": days_list,
                        }
                
                # If Grok fallback also failed or disabled, log the failure
                # Note: We'll log this at the on_message level with more context
                logger.warning("⚠️ No valid date found and no time/date in description. Reminder will not be created.")
                return None

            if dt is None:
                logger.warning("⚠️ Cannot calculate reminder time: dt is None")
                return None
            offset_minutes = self._get_reminder_offset(guild_id)
            reminder_time = dt - timedelta(minutes=offset_minutes)

            # Decide recurrence: only use parse_days when explicitly provided.
            # If we have a concrete date (explicit date or parsed from description),
            # treat it as a one-off (days = []). Otherwise, require explicit days.
            if days_line:
                days_list = parse_days_string(days_line)
            else:
                if had_explicit_date or dt_from_description:
                    # For one-off events, store weekday for informational purposes
                    # This helps in the edit modal to show which day the event is on
                    weekday = str(dt.weekday())
                    days_list = [weekday]  # Store weekday for one-off events too
                else:
                    logger.warning("⚠️ No date and no days specified → reminder not created.")
                    return None

            # Log the parsed datetime and days list for debugging purposes.
            logger.debug(
                f"🕑 Parsed datetime: {dt.astimezone(BRUSSELS_TZ)} "
                f"(weekday {dt.weekday()}) → days {days_list}"
            )

            # Include footer in description if present (for storage in message field)
            footer_text = embed.footer.text if embed.footer and embed.footer.text else None
            
            # At this point we have a valid datetime; days_list contains weekday for one-off events
            return {
                "datetime": dt,
                "reminder_time": reminder_time,
                "location": location_line or "-",
                "title": embed.title or "-",
                "description": embed.description or "-",
                "footer": footer_text,  # Include footer for later use
                "days": days_list,
            }
        except Exception as e:
            logger.exception(f"❌ Parse error: {e}")
            return None

    def extract_fields_from_lines(self, lines: List[str]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        date_line = time_line = location_line = days_line = None
        for line in lines:
            lower = line.lower()
            if "date:" in lower:
                date_line = line.split(":", 1)[1].strip()
            elif "time:" in lower:
                time_line = line.split(":", 1)[1].strip()
            elif "location:" in lower or "locatie:" in lower:
                location_line = line.split(":", 1)[1].strip()
            elif "days:" in lower:
                days_line = line.split(":", 1)[1].strip()
        return date_line, time_line, location_line, days_line

    def parse_datetime(self, date_line: Optional[str], time_line: Optional[str]) -> Tuple[Optional[datetime], Optional[object]]:
        if not time_line:
            logger.warning(f"❌ No valid time found in line: {time_line}")
            return None, None

        time_match = re.search(r"^.*?(\d{1,2})[:.](\d{2})(?:\s*(CET|CEST))?.*$", time_line)
        if not time_match:
            return None, None

        hour = int(time_match.group(1))
        minute = int(time_match.group(2))
        _timezone_str = time_match.group(3) or "CET"

        tz = BRUSSELS_TZ

        if date_line:
            date_line = date_line.strip()
            numeric = re.search(r"(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?", date_line)
            if numeric:
                day = int(numeric.group(1))
                month = int(numeric.group(2))
                year = numeric.group(3)
                if year:
                    year = int(year) if len(year) == 4 else 2000 + int(year)
                else:
                    year = datetime.now(BRUSSELS_TZ).year
            else:
                date_match = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:\s+(\d{4}))?", date_line)
                if not date_match:
                    alt_match = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?", date_line)
                    if not alt_match:
                        return None, None
                    month_str, day, year = alt_match.groups()
                else:
                    day, month_str, year = date_match.groups()
                day = int(day)
                year = int(year) if year else datetime.now(BRUSSELS_TZ).year
                try:
                    month = datetime.strptime(month_str[:3], "%b").month
                except ValueError:
                    month = datetime.strptime(month_str, "%B").month
            dt = datetime(year, month, day, hour, minute, tzinfo=tz)
        else:   
            now = datetime.now(BRUSSELS_TZ)
            dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return dt, tz

    def infer_date_from_time_line(self, time_line: str) -> Optional[str]:
        numeric = re.search(r"\b(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b", time_line)
        if numeric:
            return numeric.group(1)

        month_day = re.search(
            r"\b([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:[,\s]+(\d{4}))?",
            time_line
        )
        if month_day:
            month, day, year = month_day.groups()
            parts = [day, month]
            if year:
                parts.append(year)
            return " ".join(parts)

        day_month = re.search(
            r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:[,\s]+(\d{4}))?",
            time_line
        )
        if day_month:
            day, month, year = day_month.groups()
            parts = [day, month]
            if year:
                parts.append(year)
            return " ".join(parts)

        return None

    def parse_relative_date(self, text: str) -> Optional[str]:
        """Parse relative dates like 'This Wednesday', 'Next Friday', 'Tomorrow' etc."""
        now = datetime.now(BRUSSELS_TZ)
        text_lower = text.lower()
        
        # Day name mapping
        day_map = {
            "monday": 0, "maandag": 0, "mon": 0, "ma": 0,
            "tuesday": 1, "dinsdag": 1, "tue": 1, "di": 1,
            "wednesday": 2, "woensdag": 2, "wed": 2, "woe": 2, "wo": 2,
            "thursday": 3, "donderdag": 3, "thu": 3, "do": 3,
            "friday": 4, "vrijdag": 4, "fri": 4, "vr": 4,
            "saturday": 5, "zaterdag": 5, "sat": 5, "za": 5,
            "sunday": 6, "zondag": 6, "sun": 6, "zo": 6,
        }
        
        # Try "This [day]" or "This coming [day]"
        this_match = re.search(r"\bthis\s+(?:coming\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|mon|tue|wed|thu|fri|sat|sun|ma|di|woe?|do|vr|za|zo)\b", text_lower)
        if this_match:
            day_name = this_match.group(1)
            if day_name in day_map:
                target_weekday = day_map[day_name]
                current_weekday = now.weekday()
                days_ahead = (target_weekday - current_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7  # If today is the day, assume next week
                target_date = now + timedelta(days=days_ahead)
                return target_date.strftime("%d/%m/%Y")
        
        # Try "Next [day]"
        next_match = re.search(r"\bnext\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|mon|tue|wed|thu|fri|sat|sun|ma|di|woe?|do|vr|za|zo)\b", text_lower)
        if next_match:
            day_name = next_match.group(1)
            if day_name in day_map:
                target_weekday = day_map[day_name]
                current_weekday = now.weekday()
                days_ahead = (target_weekday - current_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7  # If today is the day, assume next week
                else:
                    days_ahead += 7  # "Next" means at least one week ahead
                target_date = now + timedelta(days=days_ahead)
                return target_date.strftime("%d/%m/%Y")
        
        # Try "Tomorrow"
        if re.search(r"\btomorrow\b", text_lower) or re.search(r"\bmorgen\b", text_lower):
            target_date = now + timedelta(days=1)
            return target_date.strftime("%d/%m/%Y")
        
        # Try "Today"
        if re.search(r"\btoday\b", text_lower) or re.search(r"\bvandaag\b", text_lower):
            return now.strftime("%d/%m/%Y")
        
        return None

    def parse_days(self, days_line: Optional[str], dt: datetime) -> str:
        """Parse days line and return comma-separated string. Uses centralized parser."""
        if not days_line:
            return str(dt.weekday())
        
        # Use centralized parser
        days_list = parse_days_string(days_line)
        if days_list:
            return ",".join(sorted(set(days_list)))
        
        # Fallback to weekday of provided datetime
        logger.debug(f"⚠️ Fallback triggered in parse_days — no valid days_line: '{days_line}' → weekday of dt: {dt.strftime('%A')} ({dt.weekday()})")
        return str(dt.weekday())

    def _short_title_for_reminder_name(self, parsed: dict, max_chars: int = 50) -> str:
        """
        Derive a short, clear title for the reminder name. When the embed title is long or
        duplicates the description (everything in one line), use the first line of the
        description or the first part of the title so the reminder name stays readable.
        Kept to ~50 chars so the sent reminder embed title stays concise.
        """
        title_val = (parsed.get("title") or "").strip() or "-"
        desc_val = (parsed.get("description") or "").strip() or ""

        def trim_at_word(text: str, limit: int) -> str:
            text = text.replace("\n", " ").replace("\r", " ")
            text = " ".join(text.split())
            if len(text) <= limit:
                return text
            part = text[: limit + 1].rsplit(" ", 1)
            result = part[0] if part[0] else text[:limit]
            # When there is no space in the slice, part[0] is the whole slice (limit+1 chars)
            return result[:limit]

        # Use full title only if it's short and single-line
        title_one_line = title_val.replace("\n", " ").strip()
        if len(title_one_line) <= max_chars and "\n" not in title_val:
            return trim_at_word(title_one_line, max_chars)

        # Prefer first line of description as short title when title is long/repetitive
        if desc_val and desc_val != "-":
            first_line = desc_val.split("\n")[0].strip()
            first_line = " ".join(first_line.split())
            if first_line and len(first_line) <= max_chars:
                return first_line
            if first_line:
                return trim_at_word(first_line, max_chars)

        # Fallback: first part of title at word boundary
        return trim_at_word(title_one_line, max_chars)

    def _format_message_paragraphs(self, text: str) -> str:
        """
        When the message is one long block (no or few newlines), add paragraph breaks
        after sentence endings so the reminder description is easier to read.
        Only applies when the text looks like a single block; preserves existing structure.
        """
        if not text or not text.strip():
            return text
        # Already has structure: several newlines
        if text.count("\n") >= 2:
            return text
        # One long block: break after sentence end (e.g. ". " before capital) to avoid
        # breaking abbreviations like "P.M." we only break after lowercase + ". " + uppercase
        formatted = re.sub(r"([a-z])\.\s+([A-Z])", r"\1.\n\n\2", text)
        formatted = re.sub(r"([a-z])\?\s+([A-Z])", r"\1?\n\n\2", formatted)
        formatted = re.sub(r"([a-z])\!\s+([A-Z])", r"\1!\n\n\2", formatted)
        # Optional: break on " | " so time zones get their own line (e.g. "3 PM EST | 8 PM UK")
        formatted = re.sub(r"\s+\|\s+", "\n• ", formatted)
        return formatted.strip()

    async def store_parsed_reminder(self, parsed: dict, channel: int, created_by: int, guild_id: int, origin_channel_id: Optional[int]=None, origin_message_id: Optional[int]=None) -> None:
        dt = parsed["datetime"]
        channel = int(channel)
        created_by = int(created_by)
        origin_channel_id = int(origin_channel_id) if origin_channel_id is not None else None
        origin_message_id = int(origin_message_id) if origin_message_id is not None else None
        reminder_dt = parsed["reminder_time"].astimezone(BRUSSELS_TZ)
        event_dt = parsed["datetime"].astimezone(BRUSSELS_TZ)
        trigger_time = reminder_dt.time()
        call_time_obj = event_dt.time()
        days_arr = parsed["days"]
        if isinstance(days_arr, str):
            days_arr = [d.strip() for d in days_arr.split(",") if d.strip()]
            logger.debug(f"[DEBUG] Final days_arr for DB insert: {days_arr} ({type(days_arr)})")
        # Use a short, clear title for the reminder name (avoids long/duplicate embed titles)
        short_title = self._short_title_for_reminder_name(parsed, max_chars=50)
        title_sanitized = short_title.replace("\n", " ").replace("\r", " ").strip()
        title_sanitized = " ".join(title_sanitized.split())

        # Create reminder name with prefix
        # Discord reminder name limit is 100 chars, prefix "🤖 Auto - " is 11 chars
        prefix = "🤖 Auto - "
        max_title_length = 100 - len(prefix)
        truncated_title = title_sanitized[:max_title_length] if len(title_sanitized) > max_title_length else title_sanitized
        
        # Add ellipsis if truncated
        if len(title_sanitized) > max_title_length:
            truncated_title = truncated_title.rstrip() + "..."
        
        name = f"{prefix}{truncated_title}"
        
        # Construct message field: avoid duplication
        # For plain text messages and embeds where title is already in description, use only description
        title_val = parsed.get('title', '').strip()
        desc_val = parsed.get('description', '').strip()
        footer_val = parsed.get('footer', '').strip() if parsed.get('footer') else None
        
        # Smart duplicate detection: check if title content is already in description
        # This handles cases where title and description overlap significantly
        if title_val and desc_val and title_val != "-" and desc_val != "-":
            # Extract key words from title (remove emojis, special chars, common words)
            title_words = set(re.findall(r'\b\w{3,}\b', title_val.lower()))  # Words with 3+ chars
            desc_words = set(re.findall(r'\b\w{3,}\b', desc_val.lower()))
            
            # Calculate overlap: if >50% of title words are in description, likely duplicate
            overlap = len(title_words & desc_words)
            title_word_count = len(title_words) if title_words else 1
            overlap_ratio = overlap / title_word_count if title_word_count > 0 else 0
            
            # Also check if description starts with title or contains significant title content
            title_normalized = ' '.join(title_val.split()[:10])  # First 10 words of title
            desc_start = desc_val[:len(title_normalized) + 50]  # First part of description
            
            if overlap_ratio > 0.5 or desc_val.startswith(title_val) or title_normalized.lower() in desc_start.lower():
                # Title is already in description - use description only
                message = desc_val
            else:
                # Real embed where title and description are different - combine them
                message = f"{title_val}\n\n{desc_val}"
        elif desc_val and desc_val != "-":
            # Only description available
            message = desc_val
        elif title_val and title_val != "-":
            # Only title available
            message = title_val
        else:
            message = ""
        
        # Append footer to message if present
        if footer_val and footer_val not in message:
            message = f"{message}\n\n{footer_val}".strip() if message else footer_val

        # Add light paragraph formatting when message is one long block (no structure)
        message = self._format_message_paragraphs(message)

        location = parsed.get("location", "-")

        try:
            if not is_pool_healthy(self.db):
                raise RuntimeError("Database connection not available for store_parsed_reminder")
            async with acquire_safe(self.db) as conn:
                await conn.execute(
                    """
                    INSERT INTO reminders (
                        name, channel_id, days, message, created_by, guild_id,
                        location, origin_channel_id, origin_message_id,
                        event_time, time, call_time
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    """,
                    name,
                    channel,
                    days_arr,  # geef als array door
                    message,
                    created_by,
                    guild_id,
                    location,
                    origin_channel_id,
                    origin_message_id,
                    event_dt,
                    trigger_time,  # reminder time (T-60) as time object
                    call_time_obj  # event time (T0) as time object
                )
            
            # Log successful save
            log_channel_id = self._get_log_channel_id(guild_id)
            log_channel = self.bot.get_channel(log_channel_id)
            if isinstance(log_channel, (discord.TextChannel, discord.Thread)):
                # Create embed for cleaner log display using EmbedBuilder
                db_log_embed = EmbedBuilder.info(
                    title="Reminder Saved to Database",
                    description=f"Reminder **{name}** has been successfully stored",
                    fields=[
                        {"name": "🕒 Reminder Time", "value": f"{trigger_time.strftime('%H:%M')}", "inline": True},
                        {
                            "name": "📆 Days" if days_arr else "📆 Type",
                            "value": self.format_days_for_display(days_arr) if days_arr else "One-off event",
                            "inline": True
                        }
                    ]
                )
                if location and location != "-":
                    db_log_embed.add_field(
                        name="📍 Location",
                        value=safe_embed_text(location[:1024], 1024),
                        inline=True
                    )
                db_log_embed.set_footer(text=f"embedwatcher | Guild: {guild_id}")
                
                await log_channel.send(embed=db_log_embed)
            else:
                logger.warning("⚠️ Could not find log channel for confirmation.")
        except (pg_exceptions.ConnectionDoesNotExistError, pg_exceptions.InterfaceError, ConnectionResetError) as conn_err:
            logger.warning(f"Database connection error in store_parsed_reminder: {conn_err}")
            if self.db:
                try:
                    await self.db.close()
                except Exception:
                    pass
                self.db = None
            raise
        except RuntimeError as e:
            logger.warning(f"Database pool not available: {e}")
            raise
        except Exception as e:
            logger.exception(f"[ERROR] Reminder insert failed: {e}")

    @app_commands.command(name="debug_parse_embed", description="Parse the last embed in the channel for testing.")
    async def debug_parse_embed(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("⚠️ This command only works in servers.")
            return
        if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread)):
            await interaction.followup.send("⚠️ This command only works in text channels.")
            return
        messages = [m async for m in interaction.channel.history(limit=10)]

        for msg in messages:
            if msg.embeds:
                embed = msg.embeds[0]
                parsed = await self.parse_embed_for_reminder(embed, interaction.guild.id)
                if parsed:
                    response = (
                        f"🧠 **Parsed data:**\n"
                        f"📅 Datum: `{parsed['datetime']}`\n"
                        f"⏰ Reminder Time: `{parsed['reminder_time']}`\n"
                        f"📍 Location: `{parsed.get('location', '-')}`"
                    )
                    await interaction.followup.send(response)
                else:
                    await interaction.followup.send("❌ Could not parse embed.")
                return

        await interaction.followup.send("⚠️ No embed found in the last 10 messages.")


    def _get_announcements_channel_id(self, guild_id: int) -> int:
        return self.settings_helper.get_int("embedwatcher", "announcements_channel_id", guild_id, fallback=0)

    def _get_log_channel_id(self, guild_id: int) -> int:
        return self.settings_helper.get_int("system", "log_channel_id", guild_id, fallback=0)

    def _get_reminder_offset(self, guild_id: int) -> int:
        return self.settings_helper.get_int("embedwatcher", "reminder_offset_minutes", guild_id, fallback=60)

    def _is_gpt_fallback_enabled(self, guild_id: int) -> bool:
        return self.settings_helper.get_bool("embedwatcher", "gpt_fallback_enabled", guild_id, fallback=True)

    def _get_failed_parse_log_channel_id(self, guild_id: int) -> int:
        value = self.settings_helper.get_int("embedwatcher", "failed_parse_log_channel_id", guild_id, fallback=0)
        if value and value != 0:
            return value
        # Fallback to system log channel
        return self.settings_helper.get_int("system", "log_channel_id", guild_id, fallback=0)

    def _is_non_embed_enabled(self, guild_id: int) -> bool:
        """Check if non-embed message parsing is enabled."""
        return self.settings_helper.get_bool("embedwatcher", "non_embed_enabled", guild_id, fallback=False)

    def _is_process_bot_messages_enabled(self, guild_id: int) -> bool:
        """Check if processing bot's own messages is enabled."""
        return self.settings_helper.get_bool("embedwatcher", "process_bot_messages", guild_id, fallback=False)

    async def _check_existing_reminder_for_message(self, guild_id: int, channel_id: int, message_id: int) -> Optional[int]:
        """Check if a reminder already exists for this message to prevent duplicate processing."""
        if not is_pool_healthy(self.db):
            return None
        try:
            async with acquire_safe(self.db) as conn:
                row = await conn.fetchrow(
                    "SELECT id FROM reminders WHERE guild_id = $1 AND origin_channel_id = $2 AND origin_message_id = $3 LIMIT 1",
                    guild_id, channel_id, message_id
                )
                return row["id"] if row else None
        except RuntimeError:
            return None
        except Exception as e:
            logger.warning(f"⚠️ Error checking existing reminder: {e}")
            return None
    
    async def _check_similar_reminder_exists(self, guild_id: int, title: str, channel_id: int, minutes_threshold: int = 5) -> Optional[int]:
        """Check if a reminder with similar title already exists in the same channel within the last N minutes.
        
        This helps prevent duplicate reminders when bot_messages is enabled and the bot sees its own reminder embeds.
        """
        if not is_pool_healthy(self.db):
            return None
        try:
            # Extract key words from title (remove emojis, "Reminder:", etc.)
            title_clean = re.sub(r'[^\w\s]', ' ', title.lower())
            title_clean = re.sub(r'\b(reminder|⏰|auto)\b', '', title_clean, flags=re.IGNORECASE)
            title_words = [w for w in title_clean.split() if len(w) >= 3]  # Words with 3+ chars
            
            if not title_words:
                return None
            
            # Check for reminders in the same channel created in the last N minutes
            async with acquire_safe(self.db) as conn:
                # Get recent reminders from the same channel
                threshold_time = datetime.now(BRUSSELS_TZ) - timedelta(minutes=minutes_threshold)
                rows = await conn.fetch(
                    """
                    SELECT id, name, created_at 
                    FROM reminders 
                    WHERE guild_id = $1 
                      AND channel_id = $2 
                      AND created_at >= $3
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    guild_id, channel_id, threshold_time
                )
                
                for row in rows:
                    reminder_name = row["name"] or ""
                    # Extract key words from reminder name
                    name_clean = re.sub(r'[^\w\s]', ' ', reminder_name.lower())
                    name_clean = re.sub(r'\b(reminder|⏰|auto|🤖)\b', '', name_clean, flags=re.IGNORECASE)
                    name_words = [w for w in name_clean.split() if len(w) >= 3]
                    
                    # Check overlap: if >60% of words match, consider it similar
                    if name_words and title_words:
                        overlap = len(set(title_words) & set(name_words))
                        min_words = min(len(title_words), len(name_words))
                        if min_words > 0 and overlap / min_words >= 0.6:
                            logger.debug(f"🔍 Found similar reminder: '{reminder_name}' matches '{title}' ({overlap}/{min_words} words)")
                            return row["id"]
                
                return None
        except RuntimeError:
            return None
        except Exception as e:
            logger.warning(f"⚠️ Error checking similar reminder: {e}")
            return None

    async def _parse_with_gpt_fallback(self, embed: discord.Embed, guild_id: int) -> Optional[dict]:
        """Use Grok to parse embed when structured parsing fails."""
        try:
            from gpt.helpers import ask_gpt
            
            from utils.sanitizer import safe_prompt
            
            # Build text from embed and sanitize it
            embed_text = f"Title: {embed.title or ''}\n"
            embed_text += f"Description: {embed.description or ''}\n"
            for field in embed.fields:
                embed_text += f"{field.name}: {field.value}\n"
            
            # Sanitize embed text before sending to Grok
            safe_embed_text = safe_prompt(embed_text)
            
            # Get current date for context
            current_date = datetime.now(BRUSSELS_TZ)
            current_date_str = current_date.strftime("%d/%m/%Y")
            current_weekday = current_date.strftime("%A")
            
            prompt = f"""Extract event information from this Discord embed. Today is {current_date_str} ({current_weekday}).

Return ONLY valid JSON with these exact keys:
{{
    "date": "DD/MM/YYYY or empty string if recurring",
    "time": "HH:MM in 24h format",
    "days": "comma-separated weekday numbers (0=Monday, 6=Sunday) or empty string if one-off",
    "location": "location string or empty string"
}}

IMPORTANT: Handle relative dates like "This Wednesday", "Next Friday", "Tomorrow", "Today" by converting them to DD/MM/YYYY format based on today's date ({current_date_str}).

Examples:
- "This Wednesday" when today is Monday → calculate the date of the upcoming Wednesday
- "Next Friday" → calculate the date of Friday next week
- "Tomorrow" → {current_date + timedelta(days=1):%d/%m/%Y}
- "Today" → {current_date_str}

Embed text:
{safe_embed_text}

If you cannot extract clear date/time information, return {{"error": "cannot_parse"}}.
Return ONLY the JSON, no other text."""

            # Call Grok with structured prompt (temperature from guild settings)
            response = await ask_gpt(
                [{"role": "user", "content": prompt}],
                user_id=None,
                model=None,
                guild_id=guild_id
            )
            
            # Parse JSON response
            import json
            # Try to extract JSON from response (might have markdown code blocks)
            response_clean = response.strip()
            if response_clean.startswith("```"):
                # Remove markdown code blocks
                response_clean = response_clean.split("```")[1]
                if response_clean.startswith("json"):
                    response_clean = response_clean[4:]
                response_clean = response_clean.strip()
            elif response_clean.startswith("{"):
                # Find the JSON object
                start = response_clean.find("{")
                end = response_clean.rfind("}") + 1
                response_clean = response_clean[start:end]
            
            parsed_json = json.loads(response_clean)
            
            if parsed_json.get("error") == "cannot_parse":
                return None
            
            # Build datetime from parsed data
            date_str = parsed_json.get("date", "").strip()
            time_str = parsed_json.get("time", "").strip()
            days_str = parsed_json.get("days", "").strip()
            location = parsed_json.get("location", "").strip()
            
            if not time_str:
                return None
            
            # Parse time
            try:
                hour, minute = map(int, time_str.split(":"))
            except (ValueError, AttributeError):
                return None
            
            # Parse date if provided
            if date_str:
                try:
                    # Try DD/MM/YYYY format
                    day, month, year = map(int, date_str.split("/"))
                    dt = datetime(year, month, day, hour, minute, tzinfo=BRUSSELS_TZ)
                    days_list = []  # One-off event
                except (ValueError, AttributeError):
                    return None
            else:
                # Recurring - use current date with parsed time
                now = datetime.now(BRUSSELS_TZ)
                dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # Parse days
                if days_str:
                    days_list = [d.strip() for d in days_str.split(",") if d.strip()]
                else:
                    # Default to weekday of current time
                    days_list = [str(dt.weekday())]
            
            return {
                "datetime": dt,
                "days": days_list,
                "location": location or "-",
            }
        except Exception as e:
            logger.exception(f"❌ Grok fallback parsing failed: {e}")
            return None

    async def _log_failed_parse(self, embed: discord.Embed, guild_id: int, message: Optional[discord.Message] = None, message_type: str = "embed") -> None:
        """Log failed parse attempt to admin channel."""
        channel_id = self._get_failed_parse_log_channel_id(guild_id)
        if channel_id == 0:
            return
        
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        
        # Build embed text for logging
        embed_text = f"**Type:** {message_type.capitalize()} message\n"
        if message:
            embed_text += f"**Author:** {message.author.mention}\n"
            channel_ref = getattr(message.channel, 'mention', f"#{getattr(message.channel, 'name', 'unknown')}") if hasattr(message.channel, 'mention') else str(message.channel.id)
            embed_text += f"**Channel:** {channel_ref}\n"
            embed_text += f"**Message ID:** `{message.id}`\n"
            embed_text += f"**Jump URL:** [Go to message]({message.jump_url})\n\n"
        
        embed_text += f"**Title:** {embed.title or '—'}\n"
        embed_text += f"**Description:** {embed.description or '—'}\n"
        if embed.fields:
            embed_text += "\n**Fields:**\n"
            for field in embed.fields:
                embed_text += f"- **{field.name}:** {field.value}\n"
        
        log_embed = EmbedBuilder.warning(
            title="⚠️ Failed Parse",
            description=f"Could not parse reminder from {message_type}. Please review manually.\n\n{embed_text}"
        )
        log_embed.set_footer(text=f"embedwatcher | Guild: {guild_id}")
        
        try:
            await channel.send(embed=log_embed)
        except Exception as e:
            logger.warning(f"⚠️ Failed to log failed parse: {e}")

    async def _log_message_processed(self, message: discord.Message, status: str, reason: str, guild_id: int) -> None:
        """Log that a message was processed (successfully or not) to the log channel."""
        log_channel_id = self._get_log_channel_id(guild_id)
        if log_channel_id == 0:
            return
        
        log_channel = self.bot.get_channel(log_channel_id)
        if not isinstance(log_channel, (discord.TextChannel, discord.Thread)):
            return
        
        # Only log if log level allows it (info level for successful, warning for failed)
        from utils.logger import should_log_to_discord
        level = "warning" if status == "failed" else "info"
        if not should_log_to_discord(level, guild_id):
            return
        
        color = discord.Color.orange() if status == "failed" else discord.Color.green() if status == "success" else discord.Color.blue()
        emoji = "✅" if status == "success" else "⚠️" if status == "failed" else "⏭️"
        
        if isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            channel_ref = message.channel.mention
        else:
            channel_ref = f"#{getattr(message.channel, 'name', 'unknown')}" if hasattr(message.channel, 'name') else str(message.channel.id)
        # Use EmbedBuilder with appropriate level
        level = "warning" if status == "failed" else "success" if status == "success" else "info"
        log_embed = EmbedBuilder.log(
            title=f"{emoji} Message Processed ({status.capitalize()})",
            description=(
                f"**Type:** {'Embed' if message.embeds else 'Text'}\n"
                f"**Author:** {message.author.mention}\n"
                f"**Channel:** {channel_ref}\n"
                f"**Status:** {status}\n"
                f"**Reason:** {reason}\n"
                f"🔗 [Jump to message]({message.jump_url})"
            ),
            level=level,
            guild_id=guild_id
        )
        log_embed.set_footer(text=f"embedwatcher | Guild: {guild_id}")
        
        try:
            await log_channel.send(embed=log_embed)
        except Exception as e:
            logger.warning(f"⚠️ Failed to log message processed: {e}")


class MockSettingsService:
    def get(self, scope, key, guild_id):
        # Return default values for testing
        if scope == "embedwatcher" and (key == "reminder_offset" or key == "reminder_offset_minutes"):
            return 60  # default 60 minutes
        return None

class MockBot:
    def __init__(self):
        self.settings = MockSettingsService()

    def get_channel(self, *_):
        return None

async def parse_embed_for_reminder(embed: discord.Embed, guild_id: int = 0):
    """Convenience wrapper to parse a reminder embed outside of the cog."""
    parser = EmbedReminderWatcher(cast(commands.Bot, MockBot()))
    return await parser.parse_embed_for_reminder(embed, guild_id)

    async def cog_unload(self):
        """Called when the cog is unloaded - close the database pool."""
        if self.db:
            try:
                await self.db.close()
            except Exception:
                pass
            self.db = None

async def setup(bot):
    cog = EmbedReminderWatcher(bot)
    await cog.setup_db()  # hier maak je je eigen verbinding
    await bot.add_cog(cog)
