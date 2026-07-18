from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class BoolResponse(BaseModel):
    result: bool


class StatusResponse(BaseModel):
    result: Dict[str, Any]


class RoiPointsRequest(BaseModel):
    points: List[List[int]]


class RoiPointsResponse(BaseModel):
    result: List[List[int]]


class BaselineResponse(BaseModel):
    result: Optional[float]


class DetectorParamsRequest(BaseModel):
    params: Dict[str, Any]


class DetectorParamsResponse(BaseModel):
    result: Dict[str, Any]


class MeasurementResponse(BaseModel):
    result: Dict[str, Any]
