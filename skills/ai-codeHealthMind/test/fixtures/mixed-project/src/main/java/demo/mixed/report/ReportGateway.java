package demo.mixed.report;

import java.util.List;

public interface ReportGateway {

    List<String> rows(String tenant);

    String export(String tenant);
}
