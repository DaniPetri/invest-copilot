from pydantic import BaseModel, ConfigDict


class Contract(BaseModel):
    """Base for every wire model: unknown fields are rejected, so drift is caught early."""

    model_config = ConfigDict(extra="forbid")
