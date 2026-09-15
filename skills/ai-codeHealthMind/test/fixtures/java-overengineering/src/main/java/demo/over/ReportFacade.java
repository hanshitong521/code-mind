package demo.over;

public class ReportFacade {

    private final ReportRepository repository;

    public ReportFacade(ReportRepository repository) {
        this.repository = repository;
    }

    public Report find(String id) {
        return repository.find(id);
    }

    public void save(Report report) {
        repository.save(report);
    }

    public int count() {
        return repository.count();
    }
}
