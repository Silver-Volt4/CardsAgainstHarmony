import discord
from discord import User, TextChannel

from cah.db import Deck
from cah.game import Game
from cah.views import CreateRoomWizard


class Server:
    games: list[Game]

    def __init__(self) -> None:
        self.games = []

    async def new_game(self, owner: User, channel: TextChannel, selected_decks: list[Deck], goal: int):
        name = f"{owner.display_name}'s game"
        thread = await channel.create_thread(
            name=name, type=discord.ChannelType.private_thread
        )
        game = Game(self, owner, thread, name, selected_decks)
        game.goal_points = goal
        game.join(owner)
        self.games.append(game)
        return game

    async def end_game(self, game: Game):
        self.games.remove(game)


bot = discord.Bot()
server = Server()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.slash_command(description="Create a new game")
async def newgame(ctx: discord.ApplicationContext):
    channel = ctx.channel

    if channel.type != discord.ChannelType.text:
        await ctx.respond(
            "❌ This command can only be used in a text channel",
            ephemeral=True,
        )
        return

    view = CreateRoomWizard(server, channel, ctx.author)
    view.container = await ctx.respond(
        embed=view.get_embed(),
        view=view,
        ephemeral=True,
    )