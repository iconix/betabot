from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Channel:
    id: Optional[str] = ''
    name: Optional[str] = ''
    is_channel: Optional[bool] = False
    is_group: Optional[bool] = False
    is_im: Optional[bool] = False
    is_private: Optional[bool] = False
    created: Optional[int] = -1
    is_archived: Optional[bool] = False
    is_general: Optional[bool] = False
    num_members: Optional[int] = -1
