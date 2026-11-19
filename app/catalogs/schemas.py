from pydantic import BaseModel


class CupsOut(BaseModel):
    code: str
    name: str
    section: str
    is_dental: bool
    is_active: bool

    model_config = {"from_attributes": True}


class Cie10Out(BaseModel):
    code: str
    name: str
    is_dental: bool
    is_active: bool

    model_config = {"from_attributes": True}
