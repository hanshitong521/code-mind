package demo.clean.order;

import java.util.List;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface OrderMapper {

    List<Order> selectBatchIds(List<Long> ids);

    Order selectById(Long id);
}
