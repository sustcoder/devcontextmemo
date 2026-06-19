"""Unit tests for CLI commands — init/status/config/review/dream。"""

import datetime as dt
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from devcontext.cli.app import app
from devcontext.storage.sqlite import SQLiteStore

runner = CliRunner()


def _insert_knowledge(conn, kid, title="测试", domain="order", status="active", **kwargs):
    defaults = {
        "id": kid, "title": title, "domain": domain, "sub_domain": "",
        "granularity": "L3", "stability": "S4", "depth": "KH",
        "status": status, "confidence": 0.80, "code_verified": 1,
        "prune_priority": 0.0, "certainty": 0.5, "freshness": 0.5,
        "uri": "", "used_count": 0, "calibration_status": "uncalibrated",
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "stale_check_count": 0, "restored_count": 0,
        "evidence_level": 5, "code_active": 1, "auto_adopted_unreviewed": 0,
        "concept_tags": "[]",
    }
    defaults.update(kwargs)
    cols = ", ".join(defaults.keys())
    placeholders = ", ".join("?" * len(defaults))
    conn.execute(f"INSERT INTO knowledge_index ({cols}) VALUES ({placeholders})", list(defaults.values()))
    conn.commit()


# =============================================================================
# dev init
# =============================================================================

class TestInitCommand:
    """dev init 冷启动。"""

    def test_init_creates_dirs_and_db(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / ".devContextMemo" / "knowledge").exists()
        assert (tmp_path / ".devContextMemo" / "staging").exists()
        assert (tmp_path / ".devContextMemo" / "deprecated").exists()
        assert (tmp_path / ".devContextMemo" / "devcontextmemo.db").exists()

    def test_init_already_exists_without_force(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        (tmp_path / ".devContextMemo" / "devcontextmemo.db").touch()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 1

    def test_init_with_force_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        (tmp_path / ".devContextMemo" / "devcontextmemo.db").touch()
        result = runner.invoke(app, ["init", "--force"])
        assert result.exit_code == 0


# =============================================================================
# dev status
# =============================================================================

class TestStatusCommand:
    """dev status 状态查看。"""

    def test_status_empty_db(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db = SQLiteStore(str(tmp_path / ".devContextMemo" / "devcontextmemo.db"))
        db.init_db()
        db.close()
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "0" in result.output

    def test_status_with_data(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db_path = str(tmp_path / ".devContextMemo" / "devcontextmemo.db")
        db = SQLiteStore(db_path)
        db.init_db()
        _insert_knowledge(db.get_connection(), "k1", "幂等校验", domain="order")
        _insert_knowledge(db.get_connection(), "k2", "支付配置", domain="payment")
        db.close()
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "order" in result.output
        assert "payment" in result.output


# =============================================================================
# dev config
# =============================================================================

class TestConfigCommand:
    """dev config 配置管理。"""

    def test_config_get_all(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "get"])
        assert result.exit_code == 0
        assert "db_path" in result.output

    def test_config_get_specific(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "get", "db_path"])
        assert result.exit_code == 0
        assert "db_path" in result.output

    def test_config_get_unknown_key(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "get", "nonexistent"])
        assert result.exit_code == 1

    def test_config_set_writes_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "set", "port", "9999"])
        assert result.exit_code == 0
        env = (tmp_path / ".env").read_text()
        assert "DEVCONTEXT_PORT=9999" in env


# =============================================================================
# dev review
# =============================================================================

class TestReviewCommand:
    """dev review 审核交互。"""

    def test_review_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db = SQLiteStore(str(tmp_path / ".devContextMemo" / "devcontextmemo.db"))
        db.init_db()
        db.close()
        result = runner.invoke(app, ["review", "list"])
        assert result.exit_code == 0

    def test_review_list_with_pending(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db_path = str(tmp_path / ".devContextMemo" / "devcontextmemo.db")
        db = SQLiteStore(db_path)
        db.init_db()
        _insert_knowledge(db.get_connection(), "k1", "待审知识", status="pending_review")
        db.close()
        result = runner.invoke(app, ["review", "list"])
        assert result.exit_code == 0
        assert "k1" in result.output

    def test_review_approve_nonexistent_fails(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db = SQLiteStore(str(tmp_path / ".devContextMemo" / "devcontextmemo.db"))
        db.init_db()
        db.close()
        result = runner.invoke(app, ["review", "approve", "nonexistent"])
        assert result.exit_code == 1

    def test_review_reject_nonexistent_fails(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db = SQLiteStore(str(tmp_path / ".devContextMemo" / "devcontextmemo.db"))
        db.init_db()
        db.close()
        result = runner.invoke(app, ["review", "reject", "nonexistent"])
        assert result.exit_code == 1


# =============================================================================
# dev dream
# =============================================================================

class TestDreamCommand:
    """dev dream 巩固+校准。"""

    def test_dream_empty_db(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db = SQLiteStore(str(tmp_path / ".devContextMemo" / "devcontextmemo.db"))
        db.init_db()
        db.close()
        result = runner.invoke(app, ["dream"])
        assert result.exit_code == 0
        assert "巩固" in result.output or "扫描" in result.output

    def test_dream_dry_run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db = SQLiteStore(str(tmp_path / ".devContextMemo" / "devcontextmemo.db"))
        db.init_db()
        _insert_knowledge(db.get_connection(), "k1", "测试", status="staged",
                           confidence=0.90, code_verified=1)
        db.close()
        result = runner.invoke(app, ["dream", "--dry-run"])
        assert result.exit_code == 0
        assert "dry-run" in result.output or "dim" in result.output

    def test_dream_with_data(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".devContextMemo").mkdir()
        db_path = str(tmp_path / ".devContextMemo" / "devcontextmemo.db")
        db = SQLiteStore(db_path)
        db.init_db()
        _insert_knowledge(db.get_connection(), "k1", "高置信知识",
                           status="staged", confidence=0.90, code_verified=1)
        db.close()
        result = runner.invoke(app, ["dream"])
        assert result.exit_code == 0
        assert "巩固" in result.output


# =============================================================================
# CLI help
# =============================================================================

class TestCLIHelp:
    """CLI 帮助。"""

    def test_main_help(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "review" in result.output
        assert "dream" in result.output
        assert "status" in result.output
        assert "config" in result.output

    def test_review_help(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["review", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "approve" in result.output
        assert "reject" in result.output

    def test_config_help(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "get" in result.output
        assert "set" in result.output
