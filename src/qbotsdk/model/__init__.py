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

"""模型层的统一出口。"""

from .base import QQModel as QQModel
from .channel import Channel as Channel
from .channel import ChannelSubType as ChannelSubType
from .channel import ChannelType as ChannelType
from .channel import PrivateType as PrivateType
from .channel import SpeakPermission as SpeakPermission
from .draft import ChannelMessageDraft as ChannelMessageDraft
from .draft import GroupMessageDraft as GroupMessageDraft
from .draft import GroupMessageType as GroupMessageType
from .draft import InputNotify as InputNotify
from .draft import MessageMarkdown as MessageMarkdown
from .draft import MessageReference as MessageReference
from .draft import UserMessageDraft as UserMessageDraft
from .draft import UserMessageType as UserMessageType
from .event import ApiProtocol as ApiProtocol
from .event import AuthorizeData as AuthorizeData
from .event import C2CMessageCreate as C2CMessageCreate
from .event import C2CMsgReceive as C2CMsgReceive
from .event import C2CMsgReject as C2CMsgReject
from .event import ChannelCreate as ChannelCreate
from .event import ChannelDelete as ChannelDelete
from .event import ChannelEvent as ChannelEvent
from .event import ChannelMessageCreate as ChannelMessageCreate
from .event import ChannelSender as ChannelSender
from .event import ChannelUpdate as ChannelUpdate
from .event import ChatSender as ChatSender
from .event import DirectMessageCreate as DirectMessageCreate
from .event import EventModel as EventModel
from .event import FriendAdd as FriendAdd
from .event import FriendAuthor as FriendAuthor
from .event import FriendDel as FriendDel
from .event import GroupAddRobot as GroupAddRobot
from .event import GroupAtMessageCreate as GroupAtMessageCreate
from .event import GroupDelRobot as GroupDelRobot
from .event import GroupJoinRequest as GroupJoinRequest
from .event import GroupMemberAdd as GroupMemberAdd
from .event import GroupMemberRemove as GroupMemberRemove
from .event import GroupMessageCreate as GroupMessageCreate
from .event import GroupMsgReceive as GroupMsgReceive
from .event import GroupMsgReject as GroupMsgReject
from .event import GroupSender as GroupSender
from .event import GuildCreate as GuildCreate
from .event import GuildDelete as GuildDelete
from .event import GuildEvent as GuildEvent
from .event import GuildMessageCreate as GuildMessageCreate
from .event import GuildUpdate as GuildUpdate
from .event import InteractionCode as InteractionCode
from .event import InteractionCreate as InteractionCreate
from .event import InteractionData as InteractionData
from .event import InteractionMessageScene as InteractionMessageScene
from .event import InteractionResolved as InteractionResolved
from .event import InteractionResponder as InteractionResponder
from .event import InteractionType as InteractionType
from .event import MessageAudit as MessageAudit
from .event import MessageAuditPass as MessageAuditPass
from .event import MessageAuditReject as MessageAuditReject
from .event import ReadyEvent as ReadyEvent
from .event import RenderedMentions as RenderedMentions
from .event import ResumedEvent as ResumedEvent
from .event import UnknownEvent as UnknownEvent
from .event import parse_event as parse_event
from .group import GlobalMuteRule as GlobalMuteRule
from .group import Group as Group
from .group import GroupBotState as GroupBotState
from .group import GroupMember as GroupMember
from .group import GroupMemberRole as GroupMemberRole
from .group import GroupMembersPage as GroupMembersPage
from .group import GroupMuteState as GroupMuteState
from .group import MemberMuteState as MemberMuteState
from .group import MuteMode as MuteMode
from .group import MuteRecurringRule as MuteRecurringRule
from .group import MuteScheduleRule as MuteScheduleRule
from .group import RecvMsgSetting as RecvMsgSetting
from .guild import Guild as Guild
from .join_request import AutoApproved as AutoApproved
from .join_request import JoinRequest as JoinRequest
from .join_request import JoinRequestAction as JoinRequestAction
from .join_request import JoinRequestPage as JoinRequestPage
from .join_request import ReviewQA as ReviewQA
from .join_request import VerifyInfo as VerifyInfo
from .keyboard import Button as Button
from .keyboard import ButtonAction as ButtonAction
from .keyboard import ButtonActionType as ButtonActionType
from .keyboard import ButtonPermission as ButtonPermission
from .keyboard import ButtonPermissionType as ButtonPermissionType
from .keyboard import ButtonRenderData as ButtonRenderData
from .keyboard import ButtonStyle as ButtonStyle
from .keyboard import Keyboard as Keyboard
from .keyboard import KeyboardContent as KeyboardContent
from .keyboard import KeyboardRow as KeyboardRow
from .markup import AtEveryone as AtEveryone
from .markup import AtUser as AtUser
from .markup import ChannelLink as ChannelLink
from .markup import CommandEnter as CommandEnter
from .markup import CommandInput as CommandInput
from .markup import EmojiMarkup as EmojiMarkup
from .markup import PlainText as PlainText
from .markup import TextChain as TextChain
from .markup import TextNode as TextNode
from .media import FileType as FileType
from .media import MediaInfo as MediaInfo
from .media import UploadConfig as UploadConfig
from .media import UploadedFile as UploadedFile
from .media import UploadPart as UploadPart
from .media import UploadPrepare as UploadPrepare
from .member import Member as Member
from .message import GroupMessageReceipt as GroupMessageReceipt
from .message import Message as Message
from .message import MessageAttachment as MessageAttachment
from .message import MessageExtInfo as MessageExtInfo
from .message import MessageReceipt as MessageReceipt
from .message import UserMessageReceipt as UserMessageReceipt
from .reaction import Emoji as Emoji
from .reaction import EmojiType as EmojiType
from .reaction import MessageReaction as MessageReaction
from .reaction import ReactionTarget as ReactionTarget
from .reaction import ReactionTargetType as ReactionTargetType
from .reaction import ReactionUsers as ReactionUsers
from .role import Role as Role
from .role import RolesResult as RolesResult
from .scene import ARKData as ARKData
from .scene import Attachment as Attachment
from .scene import ElementAuthor as ElementAuthor
from .scene import MessageElement as MessageElement
from .scene import MessageScene as MessageScene
from .token import Token as Token
from .user import C2CUser as C2CUser
from .user import GroupUser as GroupUser
from .user import GuildUser as GuildUser
from .user import MentionUser as MentionUser
from .user import User as User

__all__ = [
    "ARKData",
    "ApiProtocol",
    "AtEveryone",
    "AtUser",
    "Attachment",
    "AuthorizeData",
    "AutoApproved",
    "Button",
    "ButtonAction",
    "ButtonActionType",
    "ButtonPermission",
    "ButtonPermissionType",
    "ButtonRenderData",
    "ButtonStyle",
    "C2CMessageCreate",
    "C2CMsgReceive",
    "C2CMsgReject",
    "C2CUser",
    "Channel",
    "ChannelCreate",
    "ChannelDelete",
    "ChannelEvent",
    "ChannelLink",
    "ChannelMessageCreate",
    "ChannelMessageDraft",
    "ChannelSender",
    "ChannelSubType",
    "ChannelType",
    "ChannelUpdate",
    "ChatSender",
    "CommandEnter",
    "CommandInput",
    "DirectMessageCreate",
    "ElementAuthor",
    "Emoji",
    "EmojiMarkup",
    "EmojiType",
    "EventModel",
    "FileType",
    "FriendAdd",
    "FriendAuthor",
    "FriendDel",
    "GlobalMuteRule",
    "Group",
    "GroupAddRobot",
    "GroupAtMessageCreate",
    "GroupBotState",
    "GroupDelRobot",
    "GroupJoinRequest",
    "GroupMember",
    "GroupMemberAdd",
    "GroupMemberRemove",
    "GroupMemberRole",
    "GroupMembersPage",
    "GroupMessageCreate",
    "GroupMessageDraft",
    "GroupMessageReceipt",
    "GroupMessageType",
    "GroupMsgReceive",
    "GroupMsgReject",
    "GroupMuteState",
    "GroupSender",
    "GroupUser",
    "Guild",
    "GuildCreate",
    "GuildDelete",
    "GuildEvent",
    "GuildMessageCreate",
    "GuildUpdate",
    "GuildUser",
    "InputNotify",
    "InteractionCode",
    "InteractionCreate",
    "InteractionData",
    "InteractionMessageScene",
    "InteractionResolved",
    "InteractionResponder",
    "InteractionType",
    "JoinRequest",
    "JoinRequestAction",
    "JoinRequestPage",
    "Keyboard",
    "KeyboardContent",
    "KeyboardRow",
    "MediaInfo",
    "Member",
    "MemberMuteState",
    "MentionUser",
    "Message",
    "MessageAttachment",
    "MessageAudit",
    "MessageAuditPass",
    "MessageAuditReject",
    "MessageElement",
    "MessageExtInfo",
    "MessageMarkdown",
    "MessageReaction",
    "MessageReceipt",
    "MessageReference",
    "MessageScene",
    "MuteMode",
    "MuteRecurringRule",
    "MuteScheduleRule",
    "PlainText",
    "PrivateType",
    "QQModel",
    "ReactionTarget",
    "ReactionTargetType",
    "ReactionUsers",
    "ReadyEvent",
    "RecvMsgSetting",
    "RenderedMentions",
    "ResumedEvent",
    "ReviewQA",
    "Role",
    "RolesResult",
    "SpeakPermission",
    "TextChain",
    "TextNode",
    "Token",
    "UnknownEvent",
    "UploadConfig",
    "UploadPart",
    "UploadPrepare",
    "UploadedFile",
    "User",
    "UserMessageDraft",
    "UserMessageReceipt",
    "UserMessageType",
    "VerifyInfo",
    "parse_event",
]
