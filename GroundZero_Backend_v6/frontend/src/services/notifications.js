import { Platform } from "react-native";
import * as Notifications from "expo-notifications";

export const NOTIFICATION_CATEGORY = "GROUNDZERO_PLACE";
export const READ_ALOUD_ACTION = "READ_ALOUD";

export async function configureNotifications() {
  try {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });

    await Notifications.setNotificationCategoryAsync(NOTIFICATION_CATEGORY, [
      {
        identifier: READ_ALOUD_ACTION,
        buttonTitle: "Read aloud",
        options: { opensAppToForeground: true },
      },
    ]);

    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("groundzero-trip", {
        name: "Ground Zero trip guidance",
        importance: Notifications.AndroidImportance.DEFAULT,
        sound: undefined,
      });
    }

    const current = await Notifications.getPermissionsAsync();
    if (current.granted) return true;
    const asked = await Notifications.requestPermissionsAsync();
    return asked.granted;
  } catch {
    return false;
  }
}

export async function notifyPlace({ title, body, voiceText, placeId }) {
  try {
    return await Notifications.scheduleNotificationAsync({
      content: {
        title,
        body,
        data: { voiceText, placeId },
        categoryIdentifier: NOTIFICATION_CATEGORY,
        ...(Platform.OS === "android" ? { channelId: "groundzero-trip" } : {}),
      },
      trigger: null,
    });
  } catch {
    return null;
  }
}
