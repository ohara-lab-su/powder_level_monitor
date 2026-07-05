from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BoolResponse(BaseModel):
    result: bool


class StatusResponse(BaseModel):
    result: dict[str, Any]


class RoiPointsRequest(BaseModel):
    points: list[list[int]]


class RoiPointsResponse(BaseModel):
    result: list[list[int]]


class BaselineRequest(BaseModel):
    level_y: float


class BaselineResponse(BaseModel):
    result: float | None


class DetectorParamsRequest(BaseModel):
    params: dict[str, Any]


class DetectorParamsResponse(BaseModel):
    result: dict[str, Any]


class MeasurementUpdateRequest(BaseModel):
    level_y: float
    decrease_mm: float | None


class MeasurementResponse(BaseModel):
    result: dict[str, Any]