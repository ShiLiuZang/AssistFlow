"""
测试健康检查端点
验证服务状态和版本信息
"""
from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    """测试健康检查：返回200和服务信息"""
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "minihelp",
    }
