import asyncio
import random
from typing import TYPE_CHECKING

import discord
from discord import User, Embed, Color

from cah import db
from cah.db import BlackCard, WhiteCard, Deck
from cah.exceptions import AlreadyInGameException, NotInGameException, GameInProgressException, PlayerNotFoundError
from cah.player import Player
from cah.views import StartCardSelectView, GameView, CzarPickWinnerView, WinnerAnnouncedView, JoinGameView

if TYPE_CHECKING:
    from cah.bot import Server


class Game:
    server: "Server"
    name: str
    players: dict[int, Player]
    owner: discord.User
    channel: discord.Thread
    in_progress: bool

    deck_white: list[WhiteCard]
    deck_white_discard: list[WhiteCard]
    deck_black: list[BlackCard]
    deck_black_discard: list[BlackCard]

    round: int
    round_view: GameView | None
    goal_points: int
    czar_order = []
    black_card: BlackCard | None = None

    def __init__(self, server: "Server", owner: discord.User, channel: discord.Thread, name: str, decks: list[Deck]):
        self.server = server
        self.players = {}
        self.owner = owner
        self.channel = channel
        self.in_progress = False
        self.round = 0
        self.round_view = None
        self.goal_points = 5
        self.name = name

        self.deck_white = []
        self.deck_black = []
        self.deck_white_discard = []
        self.deck_black_discard = []
        for deck in decks:
            self.deck_white += [c for c in db.WhiteCard.select().where(db.WhiteCard.deck == deck)]
            self.deck_black += [c for c in db.BlackCard.select().where(db.BlackCard.deck == deck)]

    def join(self, user: discord.User):
        key = user.id
        if self.in_progress:
            raise GameInProgressException()
        if key in self.players:
            raise AlreadyInGameException()
        player = Player(user, self)
        self.players[key] = player

    def leave(self, user: discord.User):
        key = user.id
        if self.in_progress:
            raise GameInProgressException()
        if key not in self.players:
            raise NotInGameException()
        self.players.pop(key)

    async def start(self):
        random.shuffle(self.deck_white)
        random.shuffle(self.deck_black)
        self.in_progress = True
        order = [p for p in self.players.keys()]
        random.shuffle(order)
        self.czar_order = order
        for p in self.get_players():
            p.add_cards(self.draw_white_cards(10))
        await self.begin_round()

    def get_players(self):
        return self.players.values()

    def get_player(self, user: User):
        player = self.players.get(user.id, None)
        if player is None:
            raise PlayerNotFoundError()
        return player

    def get_czar(self) -> Player:
        index = (self.round - 1) % len(self.czar_order)
        return self.players[self.czar_order[index]]

    def get_unfinished_players(self):
        czar = self.get_czar()
        waiting_for = []
        for player in self.get_players():
            if player is czar or player.is_round_ready():
                continue
            waiting_for.append(player)

        return waiting_for

    def is_round_ready(self):
        return len(self.get_unfinished_players()) == 0

    def draw_white_cards(self, n: int = 1):
        if n > len(self.deck_white):
            random.shuffle(self.deck_white_discard)
            self.deck_white += self.deck_white_discard
            self.deck_white_discard = []
        cards = self.deck_white[0:n]
        del self.deck_white[0:n]
        return cards

    def draw_black_card(self):
        if len(self.deck_black_discard) == 0:
            random.shuffle(self.deck_black_discard)
            self.deck_white += self.deck_black_discard
            self.deck_black_discard = []
        head = self.deck_black.pop(0)
        self.deck_black_discard.append(head)
        return head

    async def join_phase(self):
        view = JoinGameView(self)

        view.container = await self.channel.send(
            self.owner.mention,
            embed=view.get_embed(),
            view=view,
        )

    async def begin_round(self):
        self.round += 1
        self.black_card = self.draw_black_card()
        view = StartCardSelectView(self)
        view.container = await self.channel.send(
            embed=view.get_embed(),
            view=view
        )
        self.round_view = view

    async def update_round_status(self):
        if self.is_round_ready():
            await self.round_view.update()
            container = self.round_view.container
            view = CzarPickWinnerView(self)
            view.container = container
            await container.edit(
                embed=view.get_embed(),
                view=view
            )
        else:
            await self.round_view.update()

    def has_winner(self) -> Player | None:
        for p in self.get_players():
            if p.points >= self.goal_points:
                return p
        return None

    async def round_winner(self, selected_player: Player):
        selected_player.points += 1
        container = self.round_view.container
        view = WinnerAnnouncedView(selected_player)
        view.container = container
        await container.edit(
            embed=view.get_embed(),
            view=view
        )
        await asyncio.sleep(5)
        winner = self.has_winner()

        n = self.black_card.get_white_card_num()
        for p in self.get_players():
            self.deck_white_discard += p.round_selected_cards
            for s in p.round_selected_cards:
                p.cards.remove(s)
            p.round_selected_cards = []
            p.add_cards(self.draw_white_cards(n))

        if not winner:
            await self.begin_round()
        else:
            await self.channel.send(
                embed=Embed(
                    title=f"{winner.user.display_name} is the winner!",
                    image=winner.user.display_avatar.url,
                    color=Color.from_rgb(255, 176, 46)
                )
            )
            for p in self.get_players():
                p.points = 0
                self.deck_white += p.cards
                p.cards = []
            self.deck_white += self.deck_white_discard
            self.deck_black += self.deck_black_discard
            self.deck_white_discard = []
            self.deck_black_discard = []
            self.in_progress = False
            self.round_view = None
            self.czar_order = []
            self.black_card = None
            self.round = 0
            await self.join_phase()

    async def end_game(self):
        await self.server.end_game(self)
        await self.channel.delete()
