# Copyright (c) 2026-present Half_nothing.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""入群申请相关的数据模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from .base import QQModel

__all__ = [
    "AutoApproved",
    "JoinRequest",
    "JoinRequestAction",
    "JoinRequestPage",
    "ReviewQA",
    "VerifyInfo",
]


class JoinRequestAction(StrEnum):
    """审批动作。"""

    APPROVE = "approve"
    DECLINE = "decline"


class ReviewQA(QQModel):
    """入群验证的问答对。"""

    question: str = Field(alias="question")
    answer: str = Field(alias="answer")


class VerifyInfo(QQModel):
    """用户入群验证方式。"""

    method: str = Field(alias="method", description="verify_message / admin_review_qa")
    verify_message: str | None = Field(alias="verify_message", default=None)
    review_qa_list: list[ReviewQA] = Field(alias="review_qa_list", default_factory=list)


class AutoApproved(QQModel):
    """自动审批通过的扩展信息。"""

    strategy_id: str = Field(alias="strategy_id")


class JoinRequest(QQModel):
    """一条入群申请。"""

    join_request_id: str = Field(alias="join_request_id", description="申请 ID, 审批时要回传")
    risk_tips: str | None = Field(alias="risk_tips", default=None)
    union_openid: str | None = Field(alias="union_openid", default=None)
    member_openid: str = Field(alias="member_openid", description="申请人 openid")
    username: str = Field(alias="username", description="申请人昵称")
    apply_at: datetime = Field(alias="apply_at", description="申请时间, RFC3339")
    apply_source: str = Field(
        alias="apply_source", description="self_apply 主动申请 / invited 被邀请"
    )
    invited_by: str | None = Field(alias="invited_by", default=None)
    bot: bool = Field(alias="bot", description="申请人是否为机器人账号")
    verify_info: VerifyInfo | None = Field(alias="verify_info", default=None)


class JoinRequestPage(QQModel):
    """入群申请列表的一页。"""

    join_request_list: list[JoinRequest] = Field(alias="list")
    next_cursor: str = Field(alias="next_cursor", description="空串表示已到末页")
