// SeaTunnel과 동일한 Iceberg/HMS Java 클라이언트로 대용량 append 테이블을 준비한다.
import java.util.*;
import org.apache.hadoop.conf.Configuration;
import org.apache.iceberg.*;
import org.apache.iceberg.catalog.TableIdentifier;
import org.apache.iceberg.hive.HiveCatalog;
import org.apache.iceberg.types.Types;

public class PrepareProductionCatalog {
  public static void main(String[] args) throws Exception {
    HiveCatalog catalog = new HiveCatalog();
    catalog.setConf(new Configuration());
    Map<String,String> props = new HashMap<>();
    props.put("uri", "thrift://hms:9083");
    props.put("warehouse", "file:///lake/warehouse");
    catalog.initialize("local_hive", props);
    TableIdentifier id = TableIdentifier.of("retail", "production_orders_100m");
    if (args.length == 1 && args[0].equals("archive-empty-attempt")) {
      Table old = catalog.loadTable(id);
      if (old.currentSnapshot() != null) throw new IllegalStateException("Committed data exists: stop");
      catalog.renameTable(id, TableIdentifier.of("retail", "production_orders_100m_attempt1"));
      System.out.println("Archived empty failed attempt through HMS API.");
    } else if (args.length == 1 && args[0].equals("require-empty-append")) {
      Table existing = catalog.loadTable(id);
      if (existing.currentSnapshot() != null || !existing.schema().identifierFieldIds().isEmpty())
        throw new IllegalStateException("Not an empty append table: refuse retry");
      System.out.println("Verified empty append table through HMS API.");
    } else {
      // order_id는 NOT NULL로 유지하지만 identifier field로 지정하지 않는다.
      // Iceberg identifier는 관계형 DB의 UNIQUE 제약이 아니다.
      Schema schema = new Schema(
        Types.NestedField.required(1, "order_id", Types.LongType.get()),
        Types.NestedField.optional(2, "factory_id", Types.StringType.get()),
        Types.NestedField.optional(3, "product_name", Types.StringType.get()),
        Types.NestedField.optional(4, "quantity", Types.IntegerType.get()),
        Types.NestedField.optional(5, "order_date", Types.DateType.get()),
        Types.NestedField.optional(6, "status", Types.StringType.get()));
      Map<String,String> write = new HashMap<>();
      write.put("format-version", "2");
      write.put("write.parquet.compression-codec", "zstd");
      write.put("write.target-file-size-bytes", "134217728");
      write.put("write.parquet.row-group-size-bytes", "16777216");
      Table table = catalog.createTable(id, schema, PartitionSpec.unpartitioned(),
        "file:///lake/warehouse/retail.db/production_orders_100m_append", write);
      System.out.println("Created append table; identifier fields=" + table.schema().identifierFieldIds());
    }
    catalog.close();
  }
}
