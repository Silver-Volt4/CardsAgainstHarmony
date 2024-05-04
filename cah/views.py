import random
from typing import TYPE_CHECKING

from discord import ButtonStyle, Interaction, Embed, Color, EmbedAuthor, EmbedFooter, Message, TextChannel, User
from discord.ui import View, button, Button, Select
from discord.utils import escape_markdown

from cah.db import WhiteCard, BlackCard, Deck
from cah.exceptions import AlreadyInGameException, NotInGameException, PlayerNotFoundError

if TYPE_CHECKING:
    from cah.player import Player
    from cah.game import Game
    from cah.bot import Server


class GameView(View):
    container: Interaction | Message | None

    def __init__(self, *items):
        super().__init__(*items)
        self.container = None

    def get_embed(self) -> Embed:
        ...

    async def update(self, remove_view: bool = False):
        if self.container:
            await self.container.edit(embed=self.get_embed(), view=self if not remove_view else None)
            await self.container.edit(embed=self.get_embed(), view=self if not remove_view else None)


class CreateRoomWizard(GameView):
    server: "Server"
    channel: TextChannel
    owner: User
    deck_page: int
    available_decks: list[Deck]
    selected_decks: list[Deck]
    phase: int
    game: "Game"

    def get_embed(self) -> Embed:
        if self.phase == 0:
            return Embed(
                title="Select the decks you wish to use."
            )
        if self.phase == 1:
            return Embed(
                title="Select the goal number of points that must be reached to win."
            )
        if self.phase == 2:
            return Embed(
                title=f"👍 Done. See this channel: {self.game.channel.jump_url}"
            )

    def __init__(self, server: "Server", channel: TextChannel, owner: User):
        self.phase = 0
        self.server = server
        self.channel = channel
        self.owner = owner
        self.deck_page = 0
        self.available_decks = []
        self.selected_decks = []
        super().__init__()
        self.create_selector()

    def create_selector(self):
        self.phase = 0
        self.clear_items()
        select = Select()
        for deck in Deck.select().where((Deck.guild_id == self.channel.guild.id) | (Deck.guild_id == None)):
            self.available_decks.append(deck)
        max_values = 0
        for i in range(25):
            index = self.deck_page * 25 + i
            if index >= len(self.available_decks):
                break
            deck = self.available_decks[index]
            select.add_option(label=deck.name, value=str(index))
            max_values += 1
        select.callback = lambda _: self.deck_selection_made(select, _)
        select.min_values = 1
        select.max_values = max_values
        self.add_item(select)

    async def deck_selection_made(self, select: Select, interaction: Interaction):
        self.container = interaction
        self.selected_decks += [self.available_decks[int(k)] for k in select.values]
        if (len(self.available_decks) - 1) // 25 > self.deck_page:
            self.deck_page += 1
            self.create_selector()
            await self.update()
        else:
            self.create_goal_picker()
            await self.update()

    def create_goal_picker(self):
        self.phase = 1
        self.clear_items()
        select = Select()
        for i in range(2, 16):
            select.add_option(label=str(i), value=str(i))
        select.callback = lambda _: self.selected_goal(select, _)
        self.add_item(select)

    async def selected_goal(self, select: Select, interaction: Interaction):
        self.container = interaction
        goal = int(select.values[0])
        self.phase = 2
        game = await self.server.new_game(self.owner, self.channel, self.selected_decks, goal)
        self.game = game
        await game.join_phase()
        await self.update(True)
        del self


class JoinGameView(GameView):
    game: "Game"

    def __init__(self, game: "Game"):
        super().__init__()
        self.game = game

    def get_embed(self) -> Embed:
        embed = Embed(
            title=self.game.name,
            description="This is your new game room. Invite people to it by mentioning them.\n\n"
                        + "If you've been invited to this game, click the 'join' button to participate. Otherwise you will be a spectator.\n\n"
                        + f"**{self.game.owner.display_name}**, click the 'start' once everybody has joined.",
        )

        embed.add_field(name="Players", value="\n".join(
            [p.user.display_name for p in self.game.players.values()]
        ))

        return embed

    @button(label="Join", style=ButtonStyle.green, emoji="🎮")
    async def join_game(self, button: Button, interaction: Interaction):
        try:
            self.game.join(interaction.user)
        except AlreadyInGameException:
            await interaction.respond(
                "❌ You have already joined this game!", ephemeral=True
            )
            return

        await interaction.respond(
            "✅🎮 You have successfully joined!", ephemeral=True
        )
        await self.update()

    @button(label="Leave", style=ButtonStyle.red, emoji="🚪")
    async def leave_game(self, button: Button, interaction: Interaction):
        try:
            self.game.leave(interaction.user)
        except NotInGameException:
            await interaction.respond(
                "❌ You are not in this game!", ephemeral=True
            )
            return

        await interaction.respond(
            "✅🚪 You have successfully left!", ephemeral=True
        )
        await self.update()

    @button(label="Start game", style=ButtonStyle.blurple, emoji="▶️")
    async def start_game(self, button: Button, interaction: Interaction):
        user = interaction.user
        if not user == self.game.owner:
            await interaction.respond(
                f"❌ You are not the owner of this game! (That person is {self.game.owner.mention})",
                ephemeral=True,
            )
            return

        if len(self.game.get_players()) < 3:
            await interaction.respond(
                f"❌ You may not start a game if there are less than three players",
                ephemeral=True,
            )
            return

        await self.update(True)
        await self.game.start()

    @button(label="Close room", style=ButtonStyle.blurple, emoji="🗑️")
    async def close_room(self, button: Button, interaction: Interaction):
        user = interaction.user
        if not user == self.game.owner:
            await interaction.respond(
                f"❌ You are not the owner of this game! (That person is {self.game.owner.mention})",
                ephemeral=True,
            )
            return

        await self.game.end_game()


def get_card_list(cards: list[WhiteCard], selected: list[WhiteCard] = None, selected_only: bool = False) -> str:
    card_list = []
    if selected_only:
        for index, card in enumerate(selected):
            nub = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"][index % 5]
            card_list.append(f"{nub} {escape_markdown(card.text)}")
    else:
        for card in cards:
            nub = "◽"
            if selected and card in selected:
                index = selected.index(card)
                nub = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"][index % 5]
            card_list.append(f"{nub} {escape_markdown(card.text)}")
    return "\n".join(card_list)


class StartCardSelectView(GameView):
    game: "Game"

    def __init__(self, game: "Game"):
        self.game = game
        button = Button(label=f"Select {self.game.black_card.get_white_card_num()} card(s)", style=ButtonStyle.gray)
        button.callback = self.select_cards
        super().__init__(button)

    def get_embed(self) -> Embed:
        czar = self.game.get_czar()
        unfinished = [p.user.display_name for p in self.game.get_unfinished_players()]
        embed = Embed(
            title=f"Round {self.game.round}",
            description=f"# {escape_markdown(self.game.black_card.text)}",
            color=Color.from_rgb(0, 0, 0),
            author=EmbedAuthor(
                name=f"{czar.user.display_name} is the 👑 Czar",
                icon_url=czar.user.display_avatar.url
            ),
            footer=EmbedFooter(
                text=("Still waiting for: " + ", ".join(unfinished)) if len(unfinished) > 0 else "Ready!"
            )
        )
        return embed

    async def select_cards(self, interaction: Interaction):
        try:
            player = self.game.get_player(interaction.user)
        except PlayerNotFoundError:
            await interaction.respond(
                "❌ You are not a player!",
                ephemeral=True
            )
            return

        if player == self.game.get_czar():
            await interaction.respond(
                "👑 The eagerness is appreciated, but you're the Card Czar. Wait for your filthy opponents to play instead.",
                ephemeral=True
            )
            return

        if len(player.round_selected_cards) > 0:
            await interaction.respond(
                "✅ You have already finished. There is nothing for you to do.",
                ephemeral=True
            )
            return

        if player.round_selector_view:
            await player.round_selector_view.disable()

        view = SelectCardView(player, self.game.black_card)
        player.round_selector_view = view
        view.container = await interaction.respond(
            embed=view.get_embed(),
            view=view,
            ephemeral=True,
        )


class SelectCardView(GameView):
    player: "Player"
    black_card: BlackCard
    to_select: int
    selected: list[WhiteCard]

    def __init__(self, player: "Player", black_card: BlackCard):
        self.player = player
        self.black_card = black_card
        self.selected = []
        self.to_select = black_card.get_white_card_num()
        select = Select()
        for i, card in enumerate(player.cards):
            label = card.text
            if len(label) > 97:
                label = label[0:97] + "..."
            select.add_option(label=label, value=str(i))
        select.callback = lambda _: self.select_card(select, _)
        super().__init__(select)

    def get_embed(self) -> Embed:
        embed = Embed(
            title=f"Select {self.to_select} card(s)",
            description=f"# {escape_markdown(self.player.game.black_card.text)}\n\n" +
                        get_card_list(self.player.cards,
                                      self.selected,
                                      self.to_select == 0),
            color=Color.from_rgb(255, 255, 255)
        )
        if self.to_select == 0:
            embed.footer = EmbedFooter(
                text="✅ You are finished. Discard this message if you wish."
            )
        return embed

    async def select_card(self, select: Select, interaction: Interaction):
        self.container = interaction
        selected_card = self.player.cards[int(select.values[0])]
        if selected_card not in self.selected:
            self.selected.append(selected_card)
            self.to_select -= 1

        if self.to_select == 0:
            self.player.round_selected_cards = self.selected
            self.player.round_selector_view = None
            self.stop()
            await self.update(True)
            await self.player.game.update_round_status()
        else:
            await self.update()

    async def disable(self):
        self.stop()
        if self.container:
            await self.container.edit(content="➡️ Moved", embed=None, view=None)


class CzarPickWinnerView(GameView):
    game: "Game"
    players_cards: list["Player"]

    def __init__(self, game: "Game"):
        self.game = game
        czar = game.get_czar()
        self.players_cards = [p for p in game.get_players() if p != czar]
        random.shuffle(self.players_cards)
        select = Select()
        for i, player in enumerate(self.players_cards):
            label = ", ".join([p.text for p in player.round_selected_cards])
            if len(label) > 97:
                label = label[0:97] + "..."
            select.add_option(label=label, value=str(i))
        select.callback = lambda _: self.select_winner(select, _)

        super().__init__(select)

    async def select_winner(self, select: Select, interaction: Interaction):
        try:
            player = self.game.get_player(interaction.user)
        except PlayerNotFoundError:
            await interaction.respond(
                "❌ You are not a player!",
                ephemeral=True
            )
            return

        if player != self.game.get_czar():
            await interaction.respond(
                "❌ You are not the Card Czar!",
                ephemeral=True
            )
            return

        selected_player = self.players_cards[int(select.values[0])]
        await self.game.round_winner(selected_player)

    def get_player_card_list(self):
        l = []
        for p in self.players_cards:
            l.append("## ◽ " + ", ◽ ".join([escape_markdown(k.text) for k in p.round_selected_cards]))
        return "\n".join(l)

    def get_embed(self) -> Embed:
        czar = self.game.get_czar()
        embed = Embed(
            title=f"Round {self.game.round}",
            description=f"# {escape_markdown(self.game.black_card.text)}\n" + self.get_player_card_list(),
            color=Color.from_rgb(0, 0, 0),
            author=EmbedAuthor(
                name=f"{czar.user.display_name} is the 👑 Czar",
                icon_url=czar.user.display_avatar.url
            )
        )
        return embed


class WinnerAnnouncedView(GameView):
    player: "Player"

    def __init__(self, player: "Player"):
        self.player = player
        super().__init__()

    def get_embed(self) -> Embed:
        czar = self.player.game.get_czar()
        sep = "## 👑 "
        winner_cards = sep + ("\n" + sep).join([p.text for p in self.player.round_selected_cards])
        embed = Embed(
            title=f"Round {self.player.game.round}",
            description=f"# {escape_markdown(self.player.game.black_card.text)}\n" + winner_cards,
            color=Color.from_rgb(255, 176, 46),
            author=EmbedAuthor(
                name=f"{czar.user.display_name} is the 👑 Czar",
                icon_url=czar.user.display_avatar.url
            )
        )
        scoreboard = list(self.player.game.get_players())
        scoreboard.sort(key=lambda k: k.points, reverse=True)
        embed.add_field(
            name="🏅 Scoreboard",
            value="\n".join([f"{s.user.mention}: {s.points}" for s in scoreboard])
        )
        return embed
