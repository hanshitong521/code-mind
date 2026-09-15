package demo.over;

public class ReportRepository {

    public Report find(String id) {
        return new Report(id);
    }

    public void save(Report report) {
        report.touch();
    }

    public int count() {
        return 0;
    }
}
