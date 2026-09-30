package com.apkcleaner.studio;

public final class UserErrorMessagesFixture {
    public static void main(String[] args) throws java.io.IOException {
        System.out.write(UserErrorMessages.describe(new RuntimeException(args[0]), "İşlem tamamlanamadı.")
                .getBytes(java.nio.charset.StandardCharsets.UTF_8));
    }
}
