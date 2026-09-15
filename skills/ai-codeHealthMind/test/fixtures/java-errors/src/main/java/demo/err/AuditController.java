package demo.err;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AuditController {

    private static final Logger log = LoggerFactory.getLogger(AuditController.class);

    public Response<String> audit(String id) {
        try {
            return Response.success(id);
        } catch (RuntimeException ex) {
            log.error("audit failed for {}", id, ex);
            return Response.failure("audit unavailable");
        }
    }
}
