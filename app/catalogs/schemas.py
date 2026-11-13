from pydantic import BaseModel


class CupsOut(BaseModel):
    code: str
    name: str
    section: str
    is_dental: bool
    is_active: bool

    model_config = {"from_attributes": True}
