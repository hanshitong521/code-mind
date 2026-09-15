package io.micrometer.core.instrument;

public interface MeterRegistry { Counter counter(String name, String... tags); }
