SELECT d."NAME" AS namespace, t."TBL_NAME" AS table_name,
 p."PARAM_KEY", p."PARAM_VALUE"
FROM "TBLS" t
JOIN "DBS" d ON d."DB_ID"=t."DB_ID"
JOIN "TABLE_PARAMS" p ON p."TBL_ID"=t."TBL_ID"
WHERE d."NAME"='retail' AND t."TBL_NAME"='orders'
ORDER BY p."PARAM_KEY";
