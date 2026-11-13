// SeaTunnel과 동일한 Iceberg/HMS Java 클라이언트로 MinIO 위 월별 파티션 append 테이블을 준비한다.
// 사용: check(상태만 JSON 출력) | create(namespace·빈 테이블 생성, 이미 있으면 실패)
import java.util.*;
import org.apache.hadoop.conf.Configuration;
import org.apache.iceberg.*;
import org.apache.iceberg.catalog.Namespace;
import org.apache.iceberg.catalog.TableIdentifier;
import org.apache.iceberg.hive.HiveCatalog;
import org.apache.iceberg.types.Types;

public class PrepareRetailS3Catalog {
  static final String NS_LOCATION = "s3a://lakehouse/warehouse/retail_s3.db";
  static final String TABLE_LOCATION = NS_LOCATION + "/production_orders";

  public static void main(String[] args) throws Exception {
    // 접속 키는 환경변수 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY(.env.minio)를 기본 자격증명 체인이 읽는다.
    Configuration conf = new Configuration();
    conf.set("fs.s3a.endpoint", "http://minio:9000");
    conf.set("fs.s3a.endpoint.region", "us-east-1");
    conf.set("fs.s3a.path.style.access", "true");
    conf.set("fs.s3a.connection.ssl.enabled", "false");
    HiveCatalog catalog = new HiveCatalog();
    catalog.setConf(conf);
    Map<String,String> props = new HashMap<>();
    props.put("uri", "thrift://hms:9083");
    props.put("warehouse", "s3a://lakehouse/warehouse");
    catalog.initialize("local_hive_s3", props);
    Namespace ns = Namespace.of("retail_s3");
    TableIdentifier id = TableIdentifier.of(ns, "production_orders");
    String mode = args.length == 1 ? args[0] : "";

    if (mode.equals("check")) {
      if (!catalog.tableExists(id)) {
        System.out.println("STATE {\"exists\":false}");
      } else {
        Table t = catalog.loadTable(id);
        System.out.println("STATE {\"exists\":true"
          + ",\"has_snapshot\":" + (t.currentSnapshot() != null)
          + ",\"spec\":\"" + specString(t.spec()) + "\""
          + ",\"identifier_fields\":" + t.schema().identifierFieldIds().size()
          + ",\"location\":\"" + t.location() + "\"}");
      }
    } else if (mode.equals("create")) {
      if (!catalog.namespaceExists(ns)) {
        catalog.createNamespace(ns, Collections.singletonMap("location", NS_LOCATION));
      }
      String found = catalog.loadNamespaceMetadata(ns).get("location");
      if (!NS_LOCATION.equals(found)) throw new IllegalStateException("retail_s3 location is " + found);
      // order_id는 NOT NULL로 유지하지만 identifier field(PK 표시)로 지정하지 않는다.
      // 지정하면 SeaTunnel이 Delta writer를 골라 키별 위치를 메모리에 쌓는다 (docs/production-orders-100m.md).
      Schema schema = new Schema(
        Types.NestedField.required(1, "order_id", Types.LongType.get()),
        Types.NestedField.optional(2, "factory_id", Types.StringType.get()),
        Types.NestedField.optional(3, "product_name", Types.StringType.get()),
        Types.NestedField.optional(4, "quantity", Types.IntegerType.get()),
        Types.NestedField.optional(5, "order_date", Types.DateType.get()),
        Types.NestedField.optional(6, "status", Types.StringType.get()));
      // 숨은 파티셔닝: order_date를 월 단위로 잘라 파일을 나눈다. 별도 월 컬럼은 만들지 않는다.
      PartitionSpec spec = PartitionSpec.builderFor(schema).month("order_date").build();
      Map<String,String> write = new HashMap<>();
      write.put("format-version", "2");
      write.put("write.format.default", "parquet");
      write.put("write.parquet.compression-codec", "zstd");
      Table table = catalog.createTable(id, schema, spec, TABLE_LOCATION, write);
      System.out.println("Created retail_s3.production_orders spec=" + specString(table.spec())
        + " identifier fields=" + table.schema().identifierFieldIds());
    } else {
      throw new IllegalArgumentException("usage: check | create");
    }
    catalog.close();
  }

  static String specString(PartitionSpec spec) {
    StringBuilder sb = new StringBuilder("[");
    for (PartitionField f : spec.fields()) {
      if (sb.length() > 1) sb.append(',');
      sb.append(f.name()).append(':').append(f.transform()).append('(').append(f.sourceId()).append(')');
    }
    return sb.append(']').toString();
  }
}
