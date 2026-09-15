package demo.clean.pricing;

import java.math.BigDecimal;

public interface PricingStrategy {

    String name();

    BigDecimal price(BigDecimal base);
}
