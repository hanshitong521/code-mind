package org.springframework.amqp.rabbit.annotation;

public @interface RabbitListener { String[] queues() default {}; }
