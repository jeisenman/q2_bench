import asyncio
import json
from pathlib import Path

import pytest

from adapters.resource_discovery import (
    ContxClientResourceResolver,
    ContxMetadataError,
    ContxMetadataSource,
    ContxResourceQuery,
)

CLIENT_ID = "4cc7cdba-c8e7-41d7-8c5d-4b85355a543c"


def _write_metadata(root: Path) -> None:
    metadata = root / "Metadata" / "production"
    metadata.mkdir(parents=True)
    (metadata / "application_partitions.json").write_text(
        json.dumps(
            {
                "ApplicationPartitionsMetadata": [
                    {
                        "name": CLIENT_ID,
                        "zone": "us",
                        "client_group": "bank-united-client",
                        "shared_group": "shared-us",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (metadata / "datastores.json").write_text(
        json.dumps(
            {
                "DatastoresMetadata": {
                    "groups": [],
                    "instances": [
                        {
                            "name": "shared-sql",
                            "kind": "PrecisionLenderSqlServer",
                            "database": "shared_database",
                            "host_name": "shared-server",
                            "domain": "database.windows.net",
                            "groups": ["shared-us"],
                            "secret_reference": "must-not-cross-boundary",
                        },
                        {
                            "name": "bank-united-sql",
                            "kind": "PrecisionLenderSqlServer",
                            "database": "pl_sqldb_bankunited_production",
                            "host_name": "bank-united-server",
                            "domain": "database.windows.net",
                            "groups": ["bank-united-client"],
                            "secret_reference": "must-not-cross-boundary",
                        },
                        {
                            "name": "historical-adls",
                            "kind": "HistoricalDataMartADLS",
                            "host_name": "historical",
                            "domain": "dfs.core.windows.net",
                            "groups": ["shared-us"],
                        },
                        {
                            "name": "model-blob",
                            "kind": "ModelServerBlobStorage",
                            "host_name": "models",
                            "domain": "blob.core.windows.net",
                            "groups": ["shared-us"],
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )


class IdentitySource:
    async def lookup(self, identifier):
        assert identifier.value == "Bank United"
        return (
            {
                "client_name": "Bank United",
                "provisioned_client_id": CLIENT_ID,
            },
        )


def test_contx_resolver_maps_name_to_client_group_database(tmp_path: Path) -> None:
    _write_metadata(tmp_path)
    resolver = ContxClientResourceResolver(
        IdentitySource(),
        ContxMetadataSource(tmp_path),
    )

    records = asyncio.run(resolver.lookup("Bank United", resource_type="database"))

    assert records == (
        {
            "client_name": "Bank United",
            "provisioned_client_id": CLIENT_ID,
            "environment": "production",
            "zone": "us",
            "resource_set": "bank-united-client",
            "resource_name": "bank-united-sql",
            "resource_type": "PrecisionLenderSqlServer",
            "database": "pl_sqldb_bankunited_production",
            "database_server": "bank-united-server.database.windows.net",
            "routing_source": "contx-metadata",
        },
    )
    assert "secret_reference" not in records[0]


def test_contx_resolver_uses_exact_client_group_when_api_has_no_exact_name(
    tmp_path: Path,
) -> None:
    _write_metadata(tmp_path)

    class DataValidationIdentity:
        async def lookup(self, identifier):
            del identifier
            return (
                {
                    "client_name": "BankUnited - PL Data Validation",
                    "provisioned_client_id": ("f8ebcaa4-3f60-4f6e-8fa5-5b16c23032cb"),
                },
            )

    resolver = ContxClientResourceResolver(
        DataValidationIdentity(),
        ContxMetadataSource(tmp_path),
    )

    records = asyncio.run(
        resolver.lookup(
            "Bank United",
            resource_kind="PrecisionLenderSqlServer",
        )
    )

    assert records[0]["provisioned_client_id"] == CLIENT_ID
    assert records[0]["database"] == "pl_sqldb_bankunited_production"


def test_contx_source_falls_back_to_shared_group_by_kind(tmp_path: Path) -> None:
    _write_metadata(tmp_path)
    source = ContxMetadataSource(tmp_path)

    records = asyncio.run(
        source.lookup(
            ContxResourceQuery(
                client_id=CLIENT_ID,
                client_name="Bank United",
                resource_type="datalake",
            )
        )
    )

    assert records[0]["resource_name"] == "historical-adls"
    assert records[0]["resource_set"] == "shared-us"
    assert records[0]["datalake"] == "historical"


def test_contx_source_filters_one_exact_resource_kind(tmp_path: Path) -> None:
    _write_metadata(tmp_path)
    source = ContxMetadataSource(tmp_path)

    records = asyncio.run(
        source.lookup(
            ContxResourceQuery(
                client_id=CLIENT_ID,
                client_name="Bank United",
                resource_kind="HistoricalDataMartADLS",
            )
        )
    )

    assert tuple(record["resource_name"] for record in records) == ("historical-adls",)


def test_contx_source_filters_storage_resources(tmp_path: Path) -> None:
    _write_metadata(tmp_path)
    source = ContxMetadataSource(tmp_path)

    records = asyncio.run(
        source.lookup(
            ContxResourceQuery(
                client_id=CLIENT_ID,
                client_name="Bank United",
                resource_type="storage",
            )
        )
    )

    assert records[0]["resource_name"] == "model-blob"
    assert records[0]["storage"] == "models"


def test_contx_source_returns_all_effective_resource_kinds(tmp_path: Path) -> None:
    _write_metadata(tmp_path)
    source = ContxMetadataSource(tmp_path)

    records = asyncio.run(
        source.lookup(
            ContxResourceQuery(
                client_id=CLIENT_ID,
                client_name="Bank United",
            )
        )
    )

    assert tuple(record["resource_name"] for record in records) == (
        "historical-adls",
        "model-blob",
        "bank-united-sql",
    )


def test_contx_resolver_rejects_ambiguous_client_names(tmp_path: Path) -> None:
    _write_metadata(tmp_path)

    class AmbiguousIdentities:
        async def lookup(self, identifier):
            del identifier
            return (
                {
                    "client_name": "Bank United",
                    "provisioned_client_id": CLIENT_ID,
                },
                {
                    "client_name": "Bank United",
                    "provisioned_client_id": "f8ebcaa4-3f60-4f6e-8fa5-5b16c23032cb",
                },
            )

    resolver = ContxClientResourceResolver(
        AmbiguousIdentities(),
        ContxMetadataSource(tmp_path),
    )

    with pytest.raises(ContxMetadataError, match="multiple client UUIDs"):
        asyncio.run(resolver.lookup("Bank United"))


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"client_id": "not-a-uuid"}, "complete UUID"),
        ({"client_name": " "}, "client_name"),
        ({"environment": "development"}, "environment"),
        ({"resource_type": "queue"}, "resource_type"),
        ({"resource_kind": " "}, "resource_kind"),
    ],
)
def test_contx_query_rejects_invalid_boundaries(
    arguments: dict[str, str],
    message: str,
) -> None:
    values = {
        "client_id": CLIENT_ID,
        "client_name": "Bank United",
        **arguments,
    }

    with pytest.raises(ContxMetadataError, match=message):
        ContxResourceQuery(**values)


def test_contx_source_reports_missing_metadata(tmp_path: Path) -> None:
    source = ContxMetadataSource(tmp_path)

    with pytest.raises(ContxMetadataError, match="unable to load"):
        asyncio.run(source.resolve_client_id("Bank United"))


def test_contx_source_reports_unknown_client_name(tmp_path: Path) -> None:
    _write_metadata(tmp_path)
    source = ContxMetadataSource(tmp_path)

    with pytest.raises(ContxMetadataError, match="no unique client UUID"):
        asyncio.run(source.resolve_client_id("Unknown Bank"))


def test_contx_source_reports_missing_partition(tmp_path: Path) -> None:
    _write_metadata(tmp_path)
    source = ContxMetadataSource(tmp_path)

    with pytest.raises(ContxMetadataError, match="no partition"):
        asyncio.run(
            source.lookup(
                ContxResourceQuery(
                    client_id="11111111-1111-4111-8111-111111111111",
                    client_name="Unknown Bank",
                )
            )
        )
