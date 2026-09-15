package demo.over;

import java.util.List;
import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(name = "inventory")
public interface InventoryClient {

    List<String> available(String sku);
}
