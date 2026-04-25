# couchd/platforms/twitch/components/alert_commands.py
from twitchio.ext import commands

from couchd.core.clients import veil


class AlertCommands(commands.Component):
    def __init__(self):
        pass

    @commands.command(name="alerts")
    async def alerts_cmd(self, ctx: commands.Context):
        """!alerts on|off|clear — control alert overlay (broadcaster/mod only)"""
        if not ctx.author.broadcaster and not ctx.author.moderator:
            return
        args = ctx.content.split()
        sub = args[1].lower() if len(args) > 1 else ""
        if sub == "off":
            await veil.alerts_off()
            await ctx.reply("Alerts disabled.")
        elif sub == "on":
            await veil.alerts_on()
            await ctx.reply("Alerts enabled.")
        elif sub == "audio":
            mode = args[2].lower() if len(args) > 2 else ""
            if mode == "off":
                await veil.alerts_audio_off()
                await ctx.reply("Alert audio disabled.")
            elif mode == "on":
                await veil.alerts_audio_on()
                await ctx.reply("Alert audio enabled.")
            else:
                await ctx.reply("Usage: !alerts audio on | off")
        elif sub == "clear":
            await veil.clear_alert_queue()
            await ctx.reply("Alert queue cleared.")
        else:
            await ctx.reply("Usage: !alerts on | off | audio on | off | clear")
