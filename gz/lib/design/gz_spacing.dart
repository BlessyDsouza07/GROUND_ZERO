/// GroundZero's spacing scale — an 8px rhythm used for every padding,
/// gap and margin a `gz_*` component or redesigned screen introduces.
/// Screens that haven't been touched by this pass still use their own
/// literal `EdgeInsets`/`SizedBox` values; as each screen is brought
/// into the design system (see the README changelog's staged plan) its
/// spacing should move onto this scale instead of inventing new numbers.
class GZSpacing {
  const GZSpacing._();

  static const xxs = 4.0;
  static const xs = 8.0;
  static const sm = 12.0;
  static const md = 16.0;
  static const lg = 24.0;
  static const xl = 32.0;
  static const xxl = 48.0;
  static const xxxl = 64.0;
}
