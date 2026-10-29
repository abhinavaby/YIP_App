import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "org.foodbridge.app",
  appName: "FoodBridge",
  webDir: "dist",
  android: {
    allowMixedContent: false,
  },
};

export default config;
