"""Schema for `POST`/`DELETE /tweets/{id}/like` (spec §6.1, §6.3 "Likes").
"""

from __future__ import annotations

from pydantic import BaseModel


class LikeRelationship(BaseModel):
    """Response body of `POST`/`DELETE /tweets/{id}/like`: the like state
    after the call plus the tweet's updated like count, mirroring
    `FollowRelationship`'s shape so a client can update its UI from this
    single response instead of re-fetching the tweet.
    """

    liked: bool
    like_count: int
