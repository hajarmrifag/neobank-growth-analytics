from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Money = Annotated[int, Field(strict=True, ge=0, le=1_000_000_000_000)]
PositiveMoney = Annotated[int, Field(strict=True, gt=0, le=1_000_000_000_000)]


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    owner_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    currency: Literal['GBP'] = 'GBP'
    opening_balance_minor: Money = 0


class Account(BaseModel):
    id: UUID
    owner_name: str
    currency: Literal['GBP']
    opening_balance_minor: int
    balance_minor: int
    created_at: datetime


class TransferCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_account_id: UUID
    destination_account_id: UUID
    amount_minor: PositiveMoney
    currency: Literal['GBP'] = 'GBP'

    @model_validator(mode='after')
    def different_accounts(self):
        if self.source_account_id == self.destination_account_id:
            raise ValueError('Source and destination must be different accounts')
        return self


class Transfer(BaseModel):
    id: UUID
    source_account_id: UUID
    destination_account_id: UUID
    amount_minor: int
    currency: Literal['GBP']
    created_at: datetime


class HistoryItem(Transfer):
    direction: Literal['incoming', 'outgoing']


class History(BaseModel):
    items: list[HistoryItem]
    limit: int
    offset: int
