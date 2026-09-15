package demo.dead;

import java.util.List;
import org.springframework.stereotype.Component;

@Component
public class MapperSupport {

    private List<String> selectByStatus(String status) {
        return List.of();
    }
}
