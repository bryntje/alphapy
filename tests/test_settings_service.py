import asyncio

from utils.settings_service import SettingsService, SettingDefinition


def test_in_memory_settings_roundtrip():
    async def run():
        service = SettingsService(dsn=None)
        service.register(
            SettingDefinition(
                scope="test",
                key="flag",
                description="Toggle",
                value_type="bool",
                default=False,
            )
        )
        service.register(
            SettingDefinition(
                scope="test",
                key="threshold",
                description="Numeric threshold",
                value_type="int",
                default=5,
                min_value=0,
                max_value=10,
            )
        )

        await service.setup()

        assert service.get("test", "flag") is False
        assert service.get("test", "threshold") == 5

        observed: list[bool] = []

        async def listener(value: bool) -> None:
            observed.append(value)

        service.add_listener("test", "flag", listener)

        await service.set("test", "flag", True, updated_by=123)
        await asyncio.sleep(0)  # allow listener task to run

        assert service.get("test", "flag") is True
        assert service.is_overridden("test", "flag") is True
        assert observed == [True]

        await service.clear("test", "flag")
        await asyncio.sleep(0)

        assert service.get("test", "flag") is False
        assert service.is_overridden("test", "flag") is False

    asyncio.run(run())
