export const MOTOR_CHANNELS = ['C3', 'Cz', 'C4'];

export function activeChannelsFor(channelMode, allChannels) {
    if (channelMode === 'motor') {
        return allChannels.filter((ch) => MOTOR_CHANNELS.includes(ch));
    }
    if (channelMode === 'all' || channelMode === 'all_individual') {
        return allChannels;
    }
    return allChannels.includes(channelMode) ? [channelMode] : allChannels;
}
