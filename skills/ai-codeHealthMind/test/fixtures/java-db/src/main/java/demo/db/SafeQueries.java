package demo.db;

import java.util.ArrayList;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;

public class SafeQueries {

    private final SafeMapper safeMapper;

    public SafeQueries(SafeMapper safeMapper) {
        this.safeMapper = safeMapper;
    }

    public void rename(String id) {
        String statement = "UPDATE archived_rows SET label = 'x' WHERE id = #{id}";
        safeMapper.execute(statement);
    }

    public String firstPage() {
        String statement = "SELECT * FROM archived_rows LIMIT 100";
        return safeMapper.one(statement);
    }

    public List<String> prefetch(List<List<String>> chunks) {
        List<String> out = new ArrayList<>();
        for (List<String> chunk : chunks) {
            List<String> batch = safeMapper.selectList(chunk);
            out.addAll(batch);
        }
        return out;
    }

    @Mapper
    public interface SafeMapper {

        int execute(String sql);

        String one(String sql);

        List<String> selectList(List<String> ids);
    }
}
