"""app.core.instance_lock：同机只允许一个进程。"""
import pytest

from app.core import instance_lock
from app.core.instance_lock import InstanceLockError, single_instance


def test_second_holder_refused_and_released_after_exit(tmp_path):
    path = tmp_path / "sub" / "app.lock"
    with single_instance(path):
        assert path.read_text().isdigit()
        with pytest.raises(InstanceLockError, match="单进程"):
            with single_instance(path):
                pass
    with single_instance(path):  # 前一个退出后可以再次获取
        pass


def test_without_fcntl_only_warns(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(instance_lock, "fcntl", None)
    with single_instance(tmp_path / "app.lock"), single_instance(tmp_path / "app.lock"):
        pass
    assert "不支持文件锁" in caplog.text
