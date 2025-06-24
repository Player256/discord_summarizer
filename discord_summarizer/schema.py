from pydantic import BaseModel

class InputSchema(BaseModel):
    max_entries: int