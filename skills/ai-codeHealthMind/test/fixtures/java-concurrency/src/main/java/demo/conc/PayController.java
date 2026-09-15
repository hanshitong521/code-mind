package demo.conc;

import org.apache.ibatis.annotations.Mapper;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PayController {

    private final PayMapper payMapper;
    private final PayClient payClient;

    public PayController(PayMapper payMapper, PayClient payClient) {
        this.payMapper = payMapper;
        this.payClient = payClient;
    }

    @PostMapping("/pay")
    public String pay(@RequestBody PayRequest request) {
        payMapper.insert(request.toRow());
        payClient.transfer(request.getAccount(), request.getAmount());
        return "ok";
    }

    @Mapper
    public interface PayMapper {

        int insert(String row);
    }
}
