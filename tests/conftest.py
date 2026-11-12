"""外部grpc_frameがない検証環境でサービス層のみを検査する。"""
import importlib.util
import sys
import types

if importlib.util.find_spec('grpc_frame') is None:
    stub = types.ModuleType('grpc_frame')
    stub.GrpcClient = type('GrpcClient', (), {})
    sys.modules['grpc_frame'] = stub
