import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Modal, TextInput
import config
from utils.validators import validate_admin
from utils.logger import logger

# Combined check function
def is_owner_or_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        # Get application info to determine owner
        app_info = await interaction.client.application_info()
        if interaction.user.id == app_info.owner.id:
            return True
        # Check if user is in extra OWNER_IDS
        if interaction.user.id in config.OWNER_IDS:
            return True
        # Check if user has admin role (if they are a Member)
        if isinstance(interaction.user, discord.Member):
            admin_role = discord.utils.get(interaction.user.roles, id=config.ADMIN_ROLE_ID)
            if admin_role is not None:
                return True
        return False
    return app_commands.check(predicate)

class CustomSlashCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="sendto",
        description="Send a message to a specific channel with support for newlines."
    )
    @app_commands.describe(
        channel="The channel where the message should be sent",
        message="The message to send. Use \\n for a new line."
    )
    async def sendto(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: str,
    ):
        """
        Send a message to the specified channel.
        Example:
          /sendto channel:#general message:"Hello\\ncommunity!"
        """
        # Replace literal "\n" with actual newline
        formatted_message = message.replace("\\n", "\n")
        try:
            await channel.send(formatted_message)
            await interaction.response.send_message(f"Message sent to {channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)

    @app_commands.command(
        name="embed",
        description="Create and send a simple embed to a channel"
    )
    @app_commands.describe(
        channel="The channel where the embed should be sent"
    )
    async def embed(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ):
        """
        Open a modal to create and send an embed.
        """
        is_admin, error_msg = await validate_admin(interaction, raise_on_fail=False)
        if not is_admin:
            await interaction.response.send_message(
                error_msg or "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return
        
        modal = EmbedBuilderModal(channel, self.bot)
        await interaction.response.send_modal(modal)

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        """Synchronize slash commands with cooldown protection."""
        from utils.command_sync import safe_sync, format_cooldown_message
        
        guild = ctx.guild
        force = "--force" in ctx.message.content or "-f" in ctx.message.content
        
        await ctx.send("🔄 Synchronizing slash commands...")
        
        result = await safe_sync(self.bot, guild=guild, force=force)
        
        if result.success:
            sync_type = "global" if guild is None else f"guild ({guild.name})"
            await ctx.send(
                f"✅ Synced {result.command_count} {sync_type} slash commands!"
            )
        else:
            if result.cooldown_remaining:
                cooldown_msg = format_cooldown_message(result.cooldown_remaining)
                await ctx.send(
                    f"⏸️ Sync skipped: {result.error}\n"
                    f"⏰ Cooldown remaining: {cooldown_msg}\n"
                    f"💡 Use `!sync --force` to bypass cooldown (use with caution)"
                )
            else:
                await ctx.send(f"❌ Sync failed: {result.error}")
                logger.error(f"Error syncing commands: {result.error}", exc_info=True)


class EmbedBuilderModal(Modal, title="Create Embed"):
    def __init__(self, channel: discord.TextChannel, bot: commands.Bot):
        super().__init__()
        self.channel = channel
        self.bot = bot
        
        self.title_input = TextInput(
            label="Title",
            placeholder="Embed title (optional)",
            required=False,
            max_length=256
        )
        self.description_input = TextInput(
            label="Description",
            placeholder="Embed description (optional)",
            required=False,
            max_length=4000,
            style=discord.TextStyle.paragraph
        )
        self.color_input = TextInput(
            label="Color (hex)",
            placeholder="e.g., #3498db or 3498db (optional)",
            required=False,
            max_length=7
        )
        self.footer_input = TextInput(
            label="Footer",
            placeholder="Embed footer text (optional)",
            required=False,
            max_length=2048
        )
        
        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.color_input)
        self.add_item(self.footer_input)
    
    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        
        # Build embed
        embed = discord.Embed()
        
        # Title
        if self.title_input.value and self.title_input.value.strip():
            embed.title = self.title_input.value.strip()
        
        # Description
        if self.description_input.value and self.description_input.value.strip():
            embed.description = self.description_input.value.strip()
        
        # Color
        if self.color_input.value and self.color_input.value.strip():
            color_str = self.color_input.value.strip().lstrip('#')
            try:
                color_int = int(color_str, 16)
                embed.color = discord.Color(color_int)
            except ValueError:
                await interaction.followup.send(
                    f"❌ Invalid color format: `{self.color_input.value}`. Use hex format (e.g., #3498db or 3498db).",
                    ephemeral=True
                )
                return
        
        # Footer
        if self.footer_input.value and self.footer_input.value.strip():
            embed.set_footer(text=self.footer_input.value.strip())
        
        # Validate that at least title or description is provided
        if not embed.title and not embed.description:
            await interaction.followup.send(
                "❌ At least a title or description must be provided.",
                ephemeral=True
            )
            return
        
        # Send embed
        try:
            await self.channel.send(embed=embed)
            await interaction.followup.send(
                f"✅ Embed sent to {self.channel.mention}!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ I don't have permission to send messages to {self.channel.mention}.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error sending embed: {e}",
                ephemeral=True
            )



async def setup(bot: commands.Bot):
    await bot.add_cog(CustomSlashCommands(bot))

