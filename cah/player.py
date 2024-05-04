from typing import TYPE_CHECKING

import discord

from cah.db import WhiteCard
from cah.views import SelectCardView

if TYPE_CHECKING:
    from cah.game import Game


class Player:
    user: discord.User
    game: "Game"
    cards: list[WhiteCard]
    points: int

    round_selected_cards: list[WhiteCard]
    round_selector_view: SelectCardView | None

    def __init__(self, user: discord.User, game: "Game") -> None:
        self.user = user
        self.game = game
        self.points = 0
        self.cards = []
        self.round_selected_cards = []
        self.round_selector_view = None

    def add_cards(self, cards: list[WhiteCard]):
        self.cards += cards

    def request_card(self):
        self.game.channel.send()

    def is_round_ready(self):
        return len(self.round_selected_cards) > 0
