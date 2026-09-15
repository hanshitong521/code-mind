package demo.mixed.report;

import java.util.ArrayList;
import java.util.List;

public class ReportGatewayImpl implements ReportGateway {

    @Override
    public List<String> rows(String tenant) {
        return new ArrayList<>();
    }

    @Override
    public String export(String tenant) {
        return "csv:" + tenant;
    }
}
