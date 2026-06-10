'use strict';

module.exports = {
  register(/*{ strapi }*/) {},

  async bootstrap({ strapi }) {
    // Wait for the server boot to complete and tables to load, then setup locales
    process.nextTick(async () => {
      try {
        const localeService = strapi.plugin('i18n').service('locales');
        const locales = await localeService.find();
        
        const hasTr = locales.some(l => l.code === 'tr');
        if (!hasTr) {
          // Create TR and set as default
          await localeService.create({
            code: 'tr',
            name: 'Turkish (tr)',
            isDefault: true
          });
          strapi.log.info('i18n: "tr" locale successfully created as default.');
          
          // Disable default flag on existing "en" locale if present
          const enLocale = locales.find(l => l.code === 'en');
          if (enLocale && enLocale.isDefault) {
            await localeService.update(enLocale.id, {
              isDefault: false
            });
            strapi.log.info('i18n: "en" locale updated to non-default.');
          }
        } else {
          // Ensure "tr" is default if it already exists but isn't
          const trLocale = locales.find(l => l.code === 'tr');
          if (trLocale && !trLocale.isDefault) {
            await localeService.update(trLocale.id, { isDefault: true });
            
            const enLocale = locales.find(l => l.code === 'en');
            if (enLocale && enLocale.isDefault) {
              await localeService.update(enLocale.id, { isDefault: false });
            }
            strapi.log.info('i18n: "tr" has been set as default locale.');
          }
        }
        
        const hasEn = locales.some(l => l.code === 'en');
        if (!hasEn) {
          await localeService.create({
            code: 'en',
            name: 'English (en)',
            isDefault: false
          });
          strapi.log.info('i18n: "en" locale successfully created.');
        }
      } catch (error) {
        strapi.log.warn('Locale bootstrapping could not be completed: ' + error.message);
      }
    });
  },
};
