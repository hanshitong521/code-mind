package demo.conc;

import java.util.concurrent.Semaphore;
import org.springframework.stereotype.Service;

@Service
public class SafePermitGate {

    private final Semaphore permits = new Semaphore(4);

    public boolean enter(String caller) throws InterruptedException {
        permits.acquire();
        try {
            return caller != null;
        } finally {
            permits.release();
        }
    }
}
