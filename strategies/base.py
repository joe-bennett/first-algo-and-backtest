"""
Abstract base class for all strategies.
Each strategy must implement: generate_signals() and describe_signal().
"""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def generate_signals(self, data: dict) -> pd.DataFrame:
        """
        Given market/fundamental data, return a signals DataFrame.
        Columns: ticker, action (BUY/SELL/SHORT/COVER), weight, score
        """
        ...

    @abstractmethod
    def describe_signal(self, signal_row: pd.Series) -> str:
        """
        Return a human-readable explanation for a single signal row.
        This text goes directly into the email alert.
        """
        ...
