package demo.db;

import java.util.ArrayList;
import java.util.List;
import org.apache.ibatis.annotations.Mapper;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {

    private final OrderMapper orderMapper;
    private final DetailMapper detailMapper;

    public OrderQueryService(OrderMapper orderMapper, DetailMapper detailMapper) {
        this.orderMapper = orderMapper;
        this.detailMapper = detailMapper;
    }

    public List<String> detailNames() {
        List<String> orders = orderMapper.selectList(null);
        List<String> out = new ArrayList<>();
        for (String order : orders) {
            String detail = detailMapper.selectById(order);
            out.add(detail);
        }
        return out;
    }

    @Mapper
    public interface OrderMapper {

        List<String> selectList(Object wrapper);
    }

    @Mapper
    public interface DetailMapper {

        String selectById(String id);
    }
}
