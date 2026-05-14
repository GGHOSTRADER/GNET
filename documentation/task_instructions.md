
Goal : Consolidator script for features_transformer and features_volume_profile streams

constains
features_transformer is the bottle neck, so until that stream is updated, features_volume_profile is not read.

order is:
xread features_transformer, if sucesfull
xread features_volume_profile

after concatenate and print full list of features 