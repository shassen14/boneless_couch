# couchd/core/models.py
from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from couchd.core.db import Base


class GuildConfig(Base):
    __tablename__ = "guild_configs"

    # Discord IDs are huge numbers, so we MUST use BigInteger, not Integer.
    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # We can store the channel IDs here later.
    # nullable=True means it's okay if they haven't set it yet.
    welcome_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    role_select_channel_id: Mapped[int] = mapped_column(BigInteger, nullable=True)

    def __repr__(self):
        return f"<GuildConfig(guild_id={self.guild_id})>"
