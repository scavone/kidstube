"""
Phase 1: Infrastructure tests.

Validates that the project structure, Docker Compose configuration,
and environment variable setup are correct and consistent.
"""

import os
import yaml
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SERVER_ROOT = os.path.join(PROJECT_ROOT, "server")


class TestProjectStructure:
    """Verify the expected directory and file layout exists."""

    def test_docker_compose_exists(self):
        assert os.path.isfile(os.path.join(PROJECT_ROOT, "docker-compose.yml"))

    def test_env_example_exists(self):
        assert os.path.isfile(os.path.join(PROJECT_ROOT, ".env.example"))

    def test_gitignore_exists(self):
        assert os.path.isfile(os.path.join(PROJECT_ROOT, ".gitignore"))

    def test_server_directory_exists(self):
        assert os.path.isdir(SERVER_ROOT)

    def test_server_packages_exist(self):
        for pkg in ["invidious", "data", "bot", "api", "tests"]:
            pkg_dir = os.path.join(SERVER_ROOT, pkg)
            assert os.path.isdir(pkg_dir), f"Missing package dir: {pkg}"
            assert os.path.isfile(
                os.path.join(pkg_dir, "__init__.py")
            ), f"Missing __init__.py in {pkg}"

    def test_server_has_main(self):
        assert os.path.isfile(os.path.join(SERVER_ROOT, "main.py"))

    def test_server_has_dockerfile(self):
        assert os.path.isfile(os.path.join(SERVER_ROOT, "Dockerfile"))

    def test_server_has_requirements(self):
        assert os.path.isfile(os.path.join(SERVER_ROOT, "requirements.txt"))


class TestDockerCompose:
    """Validate docker-compose.yml structure and service definitions."""

    @pytest.fixture(autouse=True)
    def load_compose(self):
        compose_path = os.path.join(PROJECT_ROOT, "docker-compose.yml")
        with open(compose_path) as f:
            self.compose = yaml.safe_load(f)

    def test_has_services_key(self):
        assert "services" in self.compose

    def test_required_services_defined(self):
        expected = ["invidious", "invidious-db", "companion", "brainrotguard", "atvloadly"]
        for svc in expected:
            assert svc in self.compose["services"], f"Missing service: {svc}"

    def test_invidious_port_mapping(self):
        ports = self.compose["services"]["invidious"]["ports"]
        assert "3000:3000" in ports

    def test_brainrotguard_port_mapping(self):
        ports = self.compose["services"]["brainrotguard"]["ports"]
        assert "8080:8080" in ports

    def test_atvloadly_port_mapping(self):
        ports = self.compose["services"]["atvloadly"]["ports"]
        assert "5533:80" in ports

    def test_brainrotguard_depends_on_invidious(self):
        deps = self.compose["services"]["brainrotguard"]["depends_on"]
        assert "invidious" in deps

    def test_invidious_depends_on_db_and_companion(self):
        deps = self.compose["services"]["invidious"]["depends_on"]
        assert "invidious-db" in deps
        assert "companion" in deps

    def test_brainrotguard_builds_from_server_dir(self):
        assert self.compose["services"]["brainrotguard"]["build"] == "./server"

    def test_invidious_local_mode_enabled(self):
        config_str = self.compose["services"]["invidious"]["environment"]["INVIDIOUS_CONFIG"]
        assert "local: true" in config_str

    def test_brainrotguard_env_has_invidious_url(self):
        env_list = self.compose["services"]["brainrotguard"]["environment"]
        invidious_url_found = any("BRG_INVIDIOUS_URL=http://invidious:3000" in e for e in env_list)
        assert invidious_url_found, "BRG_INVIDIOUS_URL should point to invidious service"

    def test_brainrotguard_env_has_app_name(self):
        env_list = self.compose["services"]["brainrotguard"]["environment"]
        app_name_found = any("BRG_APP_NAME" in e for e in env_list)
        assert app_name_found, "BRG_APP_NAME should be configurable"

    def test_all_services_on_brg_network(self):
        for name, svc in self.compose["services"].items():
            networks = svc.get("networks", [])
            assert "brg" in networks, f"Service {name} is not on the 'brg' network"

    def test_volumes_defined(self):
        expected_volumes = ["invidious-db", "brg-db", "atvloadly-data"]
        for vol in expected_volumes:
            assert vol in self.compose["volumes"], f"Missing volume: {vol}"

    def test_brg_network_defined(self):
        assert "brg" in self.compose["networks"]

    def test_invidious_has_healthcheck(self):
        assert "healthcheck" in self.compose["services"]["invidious"]

    def test_postgres_has_healthcheck(self):
        assert "healthcheck" in self.compose["services"]["invidious-db"]


class TestEnvExample:
    """Validate .env.example has all expected variables."""

    @pytest.fixture(autouse=True)
    def load_env(self):
        env_path = os.path.join(PROJECT_ROOT, ".env.example")
        self.env_vars = {}
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    self.env_vars[key] = value

    def test_has_telegram_vars(self):
        assert "BRG_BOT_TOKEN" in self.env_vars
        assert "BRG_ADMIN_CHAT_ID" in self.env_vars

    def test_has_api_key(self):
        assert "BRG_API_KEY" in self.env_vars

    def test_has_timezone(self):
        assert "BRG_TIMEZONE" in self.env_vars

    def test_has_web_port(self):
        assert "BRG_WEB_PORT" in self.env_vars

    def test_has_daily_limit(self):
        assert "BRG_DAILY_LIMIT_MINUTES" in self.env_vars

    def test_has_invidious_vars(self):
        assert "INVIDIOUS_DB_PASSWORD" in self.env_vars
        assert "INVIDIOUS_COMPANION_SECRET" in self.env_vars

    def test_has_app_name(self):
        assert "BRG_APP_NAME" in self.env_vars


class TestGitignore:
    """Validate .gitignore covers sensitive and generated files."""

    @pytest.fixture(autouse=True)
    def load_gitignore(self):
        gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
        with open(gitignore_path) as f:
            self.content = f.read()

    def test_ignores_env_file(self):
        assert ".env" in self.content

    def test_ignores_pycache(self):
        assert "__pycache__" in self.content

    def test_ignores_sqlite_db(self):
        assert "*.db" in self.content

    def test_ignores_ds_store(self):
        assert ".DS_Store" in self.content

    def test_ignores_venv(self):
        assert "venv/" in self.content

    def test_ignores_xcode_derived(self):
        assert "DerivedData/" in self.content


class TestDockerfile:
    """Validate the server Dockerfile is properly structured."""

    @pytest.fixture(autouse=True)
    def load_dockerfile(self):
        df_path = os.path.join(SERVER_ROOT, "Dockerfile")
        with open(df_path) as f:
            self.content = f.read()

    def test_uses_python_base_image(self):
        assert "FROM python:" in self.content

    def test_sets_workdir(self):
        assert "WORKDIR /app" in self.content

    def test_copies_requirements(self):
        assert "requirements.txt" in self.content

    def test_installs_requirements(self):
        assert "pip install" in self.content

    def test_exposes_port(self):
        assert "EXPOSE 8080" in self.content

    def test_has_cmd(self):
        assert "CMD" in self.content


class TestRequirements:
    """Validate that required Python packages are listed."""

    @pytest.fixture(autouse=True)
    def load_requirements(self):
        self.packages = []
        for filename in ("requirements.txt", "requirements-dev.txt"):
            req_path = os.path.join(SERVER_ROOT, filename)
            if not os.path.exists(req_path):
                continue
            with open(req_path) as f:
                self.packages.extend(
                    line.split("==")[0].split("[")[0].strip().lower()
                    for line in f
                    if line.strip() and not line.startswith("#") and not line.startswith("-r")
                )

    def test_has_fastapi(self):
        assert "fastapi" in self.packages

    def test_has_uvicorn(self):
        assert "uvicorn" in self.packages

    def test_has_httpx(self):
        assert "httpx" in self.packages

    def test_has_telegram_bot(self):
        assert "python-telegram-bot" in self.packages

    def test_has_pyyaml(self):
        assert "pyyaml" in self.packages

    def test_has_pytest(self):
        assert "pytest" in self.packages
