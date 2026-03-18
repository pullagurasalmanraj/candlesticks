export const getLtpForInstrument = (inst, prices) => {

    if (!inst) return "--"

    const key = inst.instrument_key?.toUpperCase().trim()

    if (!key) return "--"

    if (!prices) return "--"

    const price = prices[key]

    if (!price) return "--"

    return price.ltp ?? "--"

}