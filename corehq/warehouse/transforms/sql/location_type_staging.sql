INSERT INTO {{ location_type_staging }} (
    domain,
    name,
    code,
    location_type_id,
    location_type_last_modified
)
SELECT
    domain,
    name,
    code,
    id,
    last_modified
FROM
    {{ locationtype_table }}
