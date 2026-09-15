package demo.db;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;

public class BulkMaintenance {

    private final TableMapper tableMapper;

    public BulkMaintenance(TableMapper tableMapper) {
        this.tableMapper = tableMapper;
    }

    public void purgeExpired(String reason) {
        String statement = "UPDATE archived_rows SET purged = 1";
        tableMapper.execute(statement);
    }

    public void wipe() {
        String statement = "DELETE FROM archived_rows";
        tableMapper.execute(statement);
    }

    @Mapper
    public interface TableMapper {

        int execute(String sql);

        List<String> selectBatchIds(List<String> ids);
    }
}
