from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BloodLink API"
    app_version: str = "1.0.0"
    # Commit the running image was built from; CI passes it as a Docker build argument.
    git_sha: str = "dev"
    database_url: str = "postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink"

    # Whole blood (red cells in CPDA-1) is usable for 42 days after collection.
    unit_shelf_life_days: int = 42
    # Minimum gap between two whole-blood donations by the same donor.
    donation_gap_days: int = 90
    # "Expiring soon" window used by the inventory view, metrics and alerts.
    expiring_window_days: int = 7
    # Units per blood group below which stock is LOW; below half of it is CRITICAL.
    safety_stock: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
