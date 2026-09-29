import { describe, expect, it } from 'vitest';
import { canCancel, cancellable, coordsFor, districtOf, emptyForm, formFromRequest, toBody, validate, workInfo } from './requestForm.js';

const catalog = {
  types: [{ type: 'Обрыв магистрали', work_type: 'emergency', skill: 'emergency' }, { type: 'Нет линка', work_type: 'local_repair', skill: 'local' }],
  districts: [{ name: 'Царицыно', lat: 55.62, lon: 37.67 }, { name: 'Бирюлёво Западное', lat: 55.59, lon: 37.64 }],
  norms: { emergency: { tech_min: 80, docs_min: 0 }, local_repair: { tech_min: 30, docs_min: 0 } },
};

describe('адрес → точка', () => {
  it('район из начала адреса', () => {
    expect(districtOf('Царицыно, ул. Луганская, 7', catalog.districts).name).toBe('Царицыно');
    expect(districtOf('бирюлево западное, Харьковская 5', catalog.districts).name).toBe('Бирюлёво Западное');
    expect(districtOf('ул. Луганская, 7', catalog.districts)).toBeNull();
  });
  it('точка рядом с центром района и одна и та же для одного адреса', () => {
    const d = catalog.districts[0];
    const [a, b] = coordsFor('Царицыно, ул. Луганская, 7', d);
    expect(Math.abs(a - d.lat) <= 0.004 && Math.abs(b - d.lon) <= 0.004).toBe(true);
    expect(coordsFor('Царицыно, ул. Луганская, 7', d)).toEqual([a, b]);
    expect(coordsFor('Царицыно, ул. Луганская, 9', d)).not.toEqual([a, b]);
  });
});

describe('форма', () => {
  it('по умолчанию: окно с ближайшего получаса на два часа, срочная, первый тип', () => {
    expect(emptyForm(13 * 60 + 20, catalog)).toMatchObject({ tw_start: '13:30', tw_end: '15:30', urgent: true, type: 'Обрыв магистрали', transport: '' });
    expect(emptyForm(13 * 60, catalog, false).urgent).toBe(false);
  });
  it('навык и работа из типа', () => {
    expect(workInfo(emptyForm(780, catalog), catalog)).toEqual({ skill: 'Аварийные', minutes: 80 });
  });
  it('проверка', () => {
    const f = emptyForm(780, catalog);
    expect(validate(f, catalog)).toEqual(['укажите адрес']);
    expect(validate({ ...f, address: 'ул. Луганская, 7' }, catalog)).toEqual(['начните адрес с района: Царицыно, Бирюлёво Западное']);
    expect(validate({ ...f, address: 'Царицыно, ул. Луганская, 7', tw_end: '13:00' }, catalog)).toEqual(['конец окна должен быть позже начала']);
    expect(validate({ ...f, address: 'Царицыно, ул. Луганская, 7' }, catalog)).toEqual([]);
  });
  it('тело запроса', () => {
    const b = toBody({ ...emptyForm(780, catalog), address: 'Царицыно, ул. Луганская, 7', transport: 'car' }, catalog);
    expect(b).toMatchObject({ address: 'Царицыно, ул. Луганская, 7', district: 'Царицыно', type: 'Обрыв магистрали',
                              skill: 'emergency', work_type: 'emergency', tw_start: '13:00', tw_end: '15:00',
                              priority: 'urgent', required_transport: 'car' });
    expect(typeof b.lat).toBe('number');
  });
  it('обратно из заявки', () => {
    expect(formFromRequest({ address: 'x', type: 'Нет линка', required_transport: null, tw_start: '10:00', tw_end: '12:00', priority: 'normal' }))
      .toEqual({ address: 'x', type: 'Нет линка', transport: '', tw_start: '10:00', tw_end: '12:00', urgent: false });
  });
});

describe('что можно отменить', () => {
  // A уже завершена к часам (11:00 ≤ 12:00) — нельзя; E в работе (11:00–13:00 захватывает 12:00) — можно,
  // как и B (ещё не начата). Отменяется и отменённая — нельзя, даже если бы её время позволяло.
  const reqs = [{ id: 'A', type: 't', address: 'a', status: 'assigned', assigned_to: 'E01', pending: [] },
                { id: 'B', type: 't', address: 'b', status: 'assigned', assigned_to: 'E01', pending: [] },
                { id: 'C', type: 't', address: 'c', status: 'unassigned', assigned_to: null, pending: ['cancel_request'] },
                { id: 'D', type: 't', address: 'd', status: 'cancelled', assigned_to: null, pending: [] },
                { id: 'E', type: 't', address: 'e', status: 'assigned', assigned_to: 'E01', pending: [] }];
  const view = { plan: { routes: [{ engineer_id: 'E01', name: 'Горбанев', stops: [
    { request_id: 'A', start: '10:00', finish: '11:00' },
    { request_id: 'E', start: '11:00', finish: '13:00' },
    { request_id: 'B', start: '15:00', finish: '16:00' }] }] } };

  it('не завершённые, без отмены — в работе тоже можно', () => {
    expect(cancellable(reqs, view, 12 * 60)).toEqual([
      { id: 'B', label: 'B · t', sub: 'Горбанев в 15:00 · b' },
      { id: 'E', label: 'E · t', sub: 'Горбанев в 11:00 · e' }]);
  });

  it('canCancel — то же правило, поштучно', () => {
    expect(canCancel(reqs[0], view, 12 * 60)).toBe(false); // A — завершена
    expect(canCancel(reqs[4], view, 12 * 60)).toBe(true); // E — в работе
    expect(canCancel(reqs[1], view, 12 * 60)).toBe(true); // B — ещё не начата
    expect(canCancel(reqs[2], view, 12 * 60)).toBe(false); // C — отмена уже в очереди
    expect(canCancel(reqs[3], view, 12 * 60)).toBe(false); // D — уже отменена
    expect(canCancel({ id: 'Z', status: 'new', pending: [] }, view, 12 * 60)).toBe(true); // нет в плане — не завершена
  });
});
