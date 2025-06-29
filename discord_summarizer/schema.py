from typing import Optional
from pydantic import BaseModel

class InputSchema(BaseModel):
    max_entries: Optional[int] = None
    channel_id: Optional[str] = None